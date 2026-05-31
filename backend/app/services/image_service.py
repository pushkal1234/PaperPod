import base64
import io
import logging
import time

from google import genai
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
    if len(image_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        logger.info(f"[OCR] Image is {len(image_bytes)/1024/1024:.1f}MB, resizing...")
    processed = _resize_image(image_bytes, mime_type)
    image_b64 = base64.b64encode(processed).decode('utf-8')

    last_error = None
    for attempt in range(3):
        try:
            response = _vision_client.models.generate_content(
                model="gemini-1.5-flash",
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
