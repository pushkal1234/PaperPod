import base64
import logging

from google import genai

from app.config import settings

logger = logging.getLogger("paperpod")

_vision_client = genai.Client(api_key=settings.GOOGLE_API_KEY) if settings.GOOGLE_API_KEY else None


def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Extract text from an image using vision OCR."""
    if not _vision_client:
        raise RuntimeError("Image text extraction is not configured on this server. Please contact support.")

    image_b64 = base64.b64encode(image_bytes).decode('utf-8')

    response = _vision_client.models.generate_content(
        model="gemini-3.5-flash",
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
