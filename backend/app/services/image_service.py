import base64
import io
import logging
import time

from google import genai
from google.genai import types
from PIL import Image

from app.config import settings

logger = logging.getLogger("paperpod")

_vision_client = genai.Client(api_key=settings.GOOGLE_API_KEY) if settings.GOOGLE_API_KEY else None

OCR_RATE_LIMIT_MSG = "You've reached PaperPod's free-tier OCR rate limit. Please try again in a few moments."
OCR_SERVICE_ERROR_MSG = "PaperPod's text extraction service is temporarily busy. Please try again shortly."
OCR_CONFIG_MSG = "Image text extraction is not configured on this server. Please contact support."

# Resize large camera images before OCR to reduce API latency
MAX_IMAGE_DIM = 1280  # max width or height in pixels
MAX_FILE_SIZE_MB = 5


def _resize_image(image_bytes: bytes, mime_type: str) -> bytes:
    """Resize camera photos to reduce OCR payload and API latency."""
    fmt = "JPEG"
    if mime_type in ("image/png", "image/webp"):
        fmt = mime_type.split("/")[1].upper()

    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if w > MAX_IMAGE_DIM or h > MAX_IMAGE_DIM:
            ratio = min(MAX_IMAGE_DIM / w, MAX_IMAGE_DIM / h)
            new_size = (int(w * ratio), int(h * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            logger.info(f"[OCR] Resized image {w}x{h} -> {new_size[0]}x{new_size[1]}")

        buf = io.BytesIO()
        # Convert to RGB if necessary (e.g., PNG with transparency)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buf, format=fmt, quality=85)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[OCR] Resize failed ({e}), sending original")
        return image_bytes


def _is_rate_limit(err_str: str) -> bool:
    low = err_str.lower()
    return any(k in low for k in ["rate_limit", "429", "quota", "too many requests", "limit exceeded"])


def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Extract text from an image using vision OCR with retry and brand-safe errors."""
    if not _vision_client:
        raise RuntimeError(OCR_CONFIG_MSG)

    # Compress/resize before sending to OCR
    original_size = len(image_bytes) / 1024
    processed = _resize_image(image_bytes, mime_type)
    processed_size = len(processed) / 1024
    logger.info(f"[OCR] Image payload: {original_size:.0f}KB -> {processed_size:.0f}KB")
    image_b64 = base64.b64encode(processed).decode('utf-8')

    last_error = None
    for attempt in range(3):
        try:
            response = _vision_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[{
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                        {"text": "Extract all readable text from this image. Preserve the layout as much as possible. Return ONLY the extracted text, no extra commentary."}
                    ]
                }],
            )
            text = response.text.strip()
            logger.info(f"[OCR] Extracted {len(text)} chars from image")
            return text
        except Exception as e:
            last_error = e
            err_str = str(e)
            if _is_rate_limit(err_str):
                wait = 15 * (attempt + 1)
                logger.warning(f"[OCR] Rate limited (attempt {attempt + 1}/3), waiting {wait}s...")
                time.sleep(wait)
            elif any(k in err_str.lower() for k in ["connection", "timeout", "unavailable", "network"]):
                wait = 10 * (attempt + 1)
                logger.warning(f"[OCR] Connection error (attempt {attempt + 1}/3), retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"[OCR] Unrecoverable error: {e}")
                raise RuntimeError(OCR_SERVICE_ERROR_MSG)

    if last_error and _is_rate_limit(str(last_error)):
        raise RuntimeError(OCR_RATE_LIMIT_MSG)
    raise RuntimeError(OCR_SERVICE_ERROR_MSG)


_FIGURE_DESC_PROMPT = (
    "You are helping turn a document into an AUDIO podcast. Below are page images "
    "from the document that contain diagrams, architecture diagrams, flowcharts, "
    "charts, or figures. For EACH page, in the order given, write a clear "
    "spoken-language description of the visual so a listener who cannot see it "
    "still understands it: name the components, how they connect or flow, and the "
    "key trend or takeaway. If a page contains an equation, state it in plain "
    "spoken form (e.g. 'loss equals the average of ...'). Ignore ordinary body "
    "paragraphs — focus only on the visual content. Start each description with "
    "'Page N:' using the page number I provide. Keep each to 2-4 sentences. If a "
    "page has no meaningful visual, skip it."
)


def describe_pdf_figures(pages: list[tuple[int, bytes]]) -> str:
    """Describe diagrams/charts/figures from rendered PDF pages in one Gemini call.

    `pages` is a list of (page_number, png_bytes). Returns a plain-text block of
    figure descriptions suitable for appending to the extracted document text so
    the podcast can narrate the visuals. Never raises — returns "" on any failure
    (vision is a best-effort enhancement, not a hard dependency).
    """
    if not _vision_client or not pages:
        return ""

    parts: list[dict] = [{"text": _FIGURE_DESC_PROMPT}]
    for page_no, img_bytes in pages:
        parts.append({"text": f"\n--- Page {page_no} ---"})
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": base64.b64encode(img_bytes).decode("utf-8"),
            }
        })

    try:
        response = _vision_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": parts}],
            config=types.GenerateContentConfig(
                max_output_tokens=2048,
                temperature=0.2,
                # Disable "thinking" so the output budget isn't spent on reasoning.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (response.text or "").strip()
        logger.info(f"[Vision] Described {len(pages)} figure page(s) -> {len(text)} chars")
        return text
    except Exception as e:  # noqa: BLE001 — best-effort enhancement
        logger.warning(f"[Vision] Figure description failed ({e}); continuing without visuals")
        return ""
