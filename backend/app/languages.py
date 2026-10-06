"""Multilingual podcast support: language detection + per-language profiles.

The podcast prompt historically never specified a language, so the model always
wrote the dialogue in English — even for a German/French/Greek document — and the
TTS then read English audio. This module lets the pipeline:

  1. detect the uploaded document's language, and
  2. for SUPPORTED languages, generate the script IN that language, voice it with
     NATIVE (correctly-accented) TTS voices, and use a localized deterministic
     outro.

Any language NOT in SUPPORTED falls back to English end-to-end (script + voices +
outro) — the current, safe behaviour. Adding a new language is just one entry in
LANGUAGE_PROFILES (name + two native voices + two outro lines).
"""

import logging

from app.config import settings

logger = logging.getLogger("paperpod")

# Native-voice languages. Host = male voice, Guest = female voice, matching the
# English default casting (Andrew/Ava). German & French use Microsoft's
# native-locale MULTILINGUAL neural voices (natively accented, high quality);
# Greek uses its standard native neural voices. The outro lines are the localized
# equivalents of the English "Guest takeaway -> Host goodbye" close.
LANGUAGE_PROFILES: dict[str, dict] = {
    "de": {
        "name": "German",
        "host_voice": "de-DE-FlorianMultilingualNeural",
        "guest_voice": "de-DE-SeraphinaMultilingualNeural",
        "host_signoff": "Host: Danke fürs Zuhören – bis zum nächsten Mal!",
        "fallback_takeaway": (
            "Guest: Entscheidend ist, wie diese Ideen zusammenhängen und was sie "
            "in der Praxis bedeuten."
        ),
    },
    "fr": {
        "name": "French",
        "host_voice": "fr-FR-RemyMultilingualNeural",
        "guest_voice": "fr-FR-VivienneMultilingualNeural",
        "host_signoff": "Host: Merci de votre écoute – à la prochaine !",
        "fallback_takeaway": (
            "Guest: L'essentiel à retenir, c'est la façon dont ces idées "
            "s'articulent et ce qu'elles signifient en pratique."
        ),
    },
    "el": {
        "name": "Greek",
        "host_voice": "el-GR-NestorasNeural",
        "guest_voice": "el-GR-AthinaNeural",
        "host_signoff": "Host: Ευχαριστούμε που μας ακούσατε – τα λέμε στο επόμενο!",
        "fallback_takeaway": (
            "Guest: Το βασικό που αξίζει να κρατήσουμε είναι πώς συνδέονται αυτές "
            "οι ιδέες και τι σημαίνουν στην πράξη."
        ),
    },
    "es": {
        "name": "Spanish",
        "host_voice": "es-ES-AlvaroNeural",
        "guest_voice": "es-ES-ElviraNeural",
        "host_signoff": "Host: Gracias por escuchar, ¡hasta la próxima!",
        "fallback_takeaway": (
            "Guest: Lo importante es cómo se conectan estas ideas y lo que "
            "significan en la práctica."
        ),
    },
    "pt": {
        "name": "Portuguese",
        "host_voice": "pt-BR-AntonioNeural",
        "guest_voice": "pt-BR-FranciscaNeural",
        "host_signoff": "Host: Obrigado por ouvir, até a próxima!",
        "fallback_takeaway": (
            "Guest: O importante é entender como essas ideias se conectam e o que "
            "significam na prática."
        ),
    },
    "it": {
        "name": "Italian",
        "host_voice": "it-IT-DiegoNeural",
        "guest_voice": "it-IT-IsabellaNeural",
        "host_signoff": "Host: Grazie per l'ascolto, alla prossima!",
        "fallback_takeaway": (
            "Guest: La cosa importante è capire come queste idee si collegano e "
            "cosa significano nella pratica."
        ),
    },
    "hi": {
        "name": "Hindi",
        "host_voice": "hi-IN-MadhurNeural",
        "guest_voice": "hi-IN-SwaraNeural",
        "host_signoff": "Host: सुनने के लिए धन्यवाद, अगली बार मिलते हैं!",
        "fallback_takeaway": (
            "Guest: ध्यान देने वाली बात यह है कि ये विचार आपस में कैसे जुड़ते हैं और "
            "व्यवहार में इनका क्या मतलब है।"
        ),
    },
    "vi": {
        "name": "Vietnamese",
        "host_voice": "vi-VN-NamMinhNeural",
        "guest_voice": "vi-VN-HoaiMyNeural",
        "host_signoff": "Host: Cảm ơn các bạn đã lắng nghe, hẹn gặp lại!",
        "fallback_takeaway": (
            "Guest: Điều quan trọng là hiểu những ý tưởng này kết nối với nhau ra "
            "sao và ý nghĩa thực tế của chúng."
        ),
    },
    "da": {
        "name": "Danish",
        "host_voice": "da-DK-JeppeNeural",
        "guest_voice": "da-DK-ChristelNeural",
        "host_signoff": "Host: Tak fordi du lyttede med – vi ses næste gang!",
        "fallback_takeaway": (
            "Guest: Det vigtige er, hvordan disse idéer hænger sammen, og hvad de "
            "betyder i praksis."
        ),
    },
    "fa": {
        "name": "Persian",
        "host_voice": "fa-IR-FaridNeural",
        "guest_voice": "fa-IR-DilaraNeural",
        "host_signoff": "Host: ممنون که گوش دادید، تا دفعهٔ بعد!",
        "fallback_takeaway": (
            "Guest: نکتهٔ مهم این است که این ایده‌ها چگونه به هم مرتبط می‌شوند و در "
            "عمل چه معنایی دارند."
        ),
    },
    "ar": {
        "name": "Arabic",
        "host_voice": "ar-SA-HamedNeural",
        "guest_voice": "ar-SA-ZariyahNeural",
        "host_signoff": "Host: شكرًا لاستماعكم، إلى اللقاء في المرة القادمة!",
        "fallback_takeaway": (
            "Guest: المهم هو كيف ترتبط هذه الأفكار معًا وماذا تعني على أرض الواقع."
        ),
    },
    "zh": {
        "name": "Chinese",
        "host_voice": "zh-CN-YunxiNeural",
        "guest_voice": "zh-CN-XiaoxiaoNeural",
        "host_signoff": "Host: 感谢收听，我们下期再见！",
        "fallback_takeaway": (
            "Guest: 关键在于理解这些观点之间的联系，以及它们在实际中的意义。"
        ),
    },
}

# Keep the English "Host:"/"Guest:" labels literal in EVERY language — they are
# parsing tags (tts_service.parse_dialogue matches ^(Host|Guest):), not spoken
# text. If the model translates them, parsing yields zero lines and the podcast
# fails. Each non-English profile's prompt instruction enforces this.


def _english_profile() -> dict:
    """English / fallback profile. Voices come from settings so env overrides and
    the existing Ava/Andrew multilingual casting still apply."""
    return {
        "name": "English",
        "host_voice": settings.TTS_VOICE_HOST,
        "guest_voice": settings.TTS_VOICE_GUEST,
        "host_signoff": "Host: Thanks for listening — see you in the next one!",
        "fallback_takeaway": (
            "Guest: The thing to hold onto is how these ideas connect and what "
            "they mean in practice."
        ),
    }


def get_language_profile(code: str | None) -> dict:
    """Return the profile for a language code, falling back to English.

    The returned dict always has: name, host_voice, guest_voice, host_signoff,
    fallback_takeaway, and is_english.
    """
    profile = dict(LANGUAGE_PROFILES.get((code or "").lower(), _english_profile()))
    profile["is_english"] = profile["name"] == "English"
    return profile


def detect_language(text: str) -> str:
    """Detect a document's base language code (e.g. 'de', 'fr', 'el', 'en').

    Returns a code only when we're confident AND we support it natively; anything
    else returns 'en' so the pipeline stays on the safe English path. Deterministic
    (seeded) so the same document always resolves to the same language — important
    because the result feeds the dedup content hash via GENERATION_VERSION.
    """
    # Feature flag: when multilingual is OFF, every document stays on the English
    # path (script, voices, outro) — the pre-feature behaviour.
    if not settings.MULTILINGUAL_ENABLED:
        return "en"

    sample = (text or "").strip()
    if len(sample) < 30:
        return "en"
    try:
        from langdetect import detect, DetectorFactory

        DetectorFactory.seed = 0  # deterministic across runs
        code = detect(sample[:3000]).split("-")[0].lower()
    except Exception as e:
        logger.warning(f"[lang] detection failed ({e}); defaulting to English")
        return "en"

    if code in LANGUAGE_PROFILES:
        logger.info(f"[lang] detected supported language '{code}' — native podcast")
        return code
    logger.info(f"[lang] detected '{code}' (no native support) — using English")
    return "en"
