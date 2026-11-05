import base64
import io
import logging
import time

from google import genai
from PIL import Image

from app.config import settings
from app.services.gemini_compat import generate_without_thinking

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


_PDF_OCR_PROMPT = (
    "These are page images from a scanned or screenshot PDF that has NO selectable "
    "text layer. Transcribe ALL readable text from every page, verbatim and in full, "
    "in natural reading order. Keep the text in its ORIGINAL language — do NOT "
    "translate or summarize. Include headings, body paragraphs, bullet points, "
    "numbered lists, table contents, captions, labels, and any text written inside "
    "diagrams, charts, or timelines. Preserve paragraph breaks. For a meaningful "
    "diagram or chart, after transcribing its text add one short '[Figure: ...]' "
    "note (in the document's language) describing what it shows. Begin each page "
    "with '--- Page N ---' using the page number I provide. Return ONLY the "
    "transcribed text, with no extra commentary."
)


# A batch's output counts as a repetition loop when it has at least this many
# lines and fewer than this share of them are distinct (a real page of text
# repeats very few lines; a loop repeats the same few lines over and over).
_OCR_LOOP_MIN_LINES = 30
_OCR_LOOP_MAX_UNIQUE_SHARE = 0.35


def _ocr_call(batch: list[tuple[int, bytes]], model: str) -> tuple[str, bool]:
    """One Gemini OCR request for a batch of pages: (text, hit_output_cap)."""
    parts: list[dict] = [{"text": _PDF_OCR_PROMPT}]
    for page_no, img_bytes in batch:
        parts.append({"text": f"\n--- Page {page_no} ---"})
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": base64.b64encode(img_bytes).decode("utf-8"),
            }
        })
    response = generate_without_thinking(
        _vision_client,
        model,
        [{"role": "user", "parts": parts}],
        # Dense multi-page transcription needs a large output budget.
        max_output_tokens=8192,
        temperature=0.0,
    )
    candidates = getattr(response, "candidates", None) or [None]
    finish = str(getattr(candidates[0], "finish_reason", "") or "")
    return (response.text or "").strip(), "MAX_TOKENS" in finish


def _looks_like_loop(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return len(lines) >= _OCR_LOOP_MIN_LINES and len(set(lines)) / len(lines) < _OCR_LOOP_MAX_UNIQUE_SHARE


def _drop_repeated_lines(text: str) -> str:
    """Keep the first occurrence of each line (last resort for one looping page)."""
    seen, out = set(), []
    for line in text.splitlines():
        key = line.strip()
        if key and key in seen:
            continue
        seen.add(key)
        out.append(line)
    return "\n".join(out)


def _transcribe_batch(batch: list[tuple[int, bytes]], models: list[str]) -> str:
    """OCR one batch. A failed request is retried once on the next Gemini model;
    a truncated or looping result is split in half and each half redone, so no
    page is silently lost to the output cap."""
    pages_label = f"{batch[0][0]}-{batch[-1][0]}" if len(batch) > 1 else str(batch[0][0])
    text, capped = "", False
    for attempt in range(2):
        model = models[min(attempt, len(models) - 1)]
        try:
            text, capped = _ocr_call(batch, model)
            break
        except Exception as e:  # noqa: BLE001 — retry once, then give up on this batch
            logger.warning(f"[OCR] Pages {pages_label} failed on {model} ({str(e)[:120]})")
            if attempt == 0:
                time.sleep(2)
    else:
        logger.error(f"[OCR] Pages {pages_label} could not be transcribed")
        return ""

    looping = _looks_like_loop(text)
    if (capped or looping) and len(batch) > 1:
        logger.warning(
            f"[OCR] Pages {pages_label} came back {'truncated' if capped else 'looping'}; "
            f"splitting the batch and redoing each half"
        )
        mid = len(batch) // 2
        halves = (_transcribe_batch(batch[:mid], models), _transcribe_batch(batch[mid:], models))
        return "\n\n".join(t for t in halves if t)
    if looping:
        logger.warning(f"[OCR] Page {pages_label} output looped; keeping each line once")
        text = _drop_repeated_lines(text)
    return text


def transcribe_pdf_pages(pages: list[tuple[int, bytes]]) -> str:
    """Full verbatim OCR of scanned/image-only PDF pages.

    Unlike :func:`describe_pdf_figures` (which writes a brief spoken *description*
    of visuals), this transcribes EVERY word on the page in the original language —
    for PDFs that are really photos/screenshots with no text layer. `pages` is a
    list of (page_number, png_bytes). Never raises — returns "" on any failure.

    Pages go to Gemini in batches of PDF_OCR_BATCH_PAGES, up to PDF_OCR_PARALLEL
    at a time. A single call for the whole document hit the 8,192-token output
    cap: a 54-page mind map came back as a few pages that then looped (8K chars,
    95% duplicate lines), so the podcast covered a sliver of it and language
    detection read the garbage as Korean.
    """
    if not _vision_client or not pages:
        return ""
    from concurrent.futures import ThreadPoolExecutor

    try:
        from app.services.llm_service import _gemini_models
        models = _gemini_models() or ["gemini-2.5-flash"]
    except Exception:  # noqa: BLE001 — fall back to the long-standing default
        models = ["gemini-2.5-flash"]

    size = max(1, settings.PDF_OCR_BATCH_PAGES)
    batches = [pages[i:i + size] for i in range(0, len(pages), size)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, min(settings.PDF_OCR_PARALLEL, len(batches)))) as pool:
        texts = list(pool.map(lambda b: _transcribe_batch(b, models), batches))
    text = "\n\n".join(t for t in texts if t).strip()
    missing = sum(len(b) for b, t in zip(batches, texts) if not t)
    logger.info(
        f"[OCR] Transcribed {len(pages)} scanned page(s) in {len(batches)} batch(es) -> "
        f"{len(text)} chars in {time.perf_counter() - t0:.1f}s"
        + (f"; {missing} page(s) could not be read" if missing else "")
    )
    return text


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
        # Thinking off, so the output budget isn't spent on reasoning.
        response = generate_without_thinking(
            _vision_client,
            "gemini-2.5-flash",
            [{"role": "user", "parts": parts}],
            max_output_tokens=2048,
            temperature=0.2,
        )
        text = (response.text or "").strip()
        logger.info(f"[Vision] Described {len(pages)} figure page(s) -> {len(text)} chars")
        return text
    except Exception as e:  # noqa: BLE001 — best-effort enhancement
        logger.warning(f"[Vision] Figure description failed ({e}); continuing without visuals")
        return ""
