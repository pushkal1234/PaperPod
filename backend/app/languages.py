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
import re

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
    "ur": {
        "name": "Urdu",
        "host_voice": "ur-PK-AsadNeural",
        "guest_voice": "ur-PK-UzmaNeural",
        "host_signoff": "Host: سننے کا شکریہ، اگلی بار ملتے ہیں!",
        "fallback_takeaway": (
            "Guest: اہم بات یہ ہے کہ یہ خیالات آپس میں کیسے جڑتے ہیں اور عملی طور پر "
            "ان کا کیا مطلب ہے۔"
        ),
    },
    "ru": {
        "name": "Russian",
        "host_voice": "ru-RU-DmitryNeural",
        "guest_voice": "ru-RU-SvetlanaNeural",
        "host_signoff": "Host: Спасибо, что слушали, до встречи в следующий раз!",
        "fallback_takeaway": (
            "Guest: Главное — понять, как эти идеи связаны между собой и что они "
            "значат на практике."
        ),
    },
    "nl": {
        "name": "Dutch",
        "host_voice": "nl-NL-MaartenNeural",
        "guest_voice": "nl-NL-ColetteNeural",
        "host_signoff": "Host: Bedankt voor het luisteren, tot de volgende keer!",
        "fallback_takeaway": (
            "Guest: Het belangrijkste is hoe deze ideeën met elkaar samenhangen en "
            "wat ze in de praktijk betekenen."
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
    "lt": {
        "name": "Lithuanian",
        "host_voice": "lt-LT-LeonasNeural",
        "guest_voice": "lt-LT-OnaNeural",
        "host_signoff": "Host: Ačiū, kad klausėtės, iki kito karto!",
        "fallback_takeaway": (
            "Guest: Svarbiausia suprasti, kaip šios idėjos susijusios tarpusavyje ir "
            "ką jos reiškia praktikoje."
        ),
    },
    # Malay = Latin-script Bahasa Melayu (Malaysia). langdetect has no 'ms', so
    # Malay docs come back as 'id' and are re-classified by _refine_code.
    "ms": {
        "name": "Malay",
        "host_voice": "ms-MY-OsmanNeural",
        "guest_voice": "ms-MY-YasminNeural",
        "host_signoff": "Host: Terima kasih kerana mendengar, jumpa lagi lain kali!",
        "fallback_takeaway": (
            "Guest: Perkara penting ialah bagaimana idea-idea ini saling berkait dan "
            "apa maknanya dalam amalan."
        ),
    },
    # Indonesian is what langdetect's 'id' means; _refine_code only moves an 'id'
    # result to Malay when Malay vocabulary outweighs Indonesian.
    "id": {
        "name": "Indonesian",
        "host_voice": "id-ID-ArdiNeural",
        "guest_voice": "id-ID-GadisNeural",
        "host_signoff": "Host: Terima kasih sudah mendengarkan, sampai jumpa lagi!",
        "fallback_takeaway": (
            "Guest: Yang penting adalah bagaimana ide-ide ini saling terhubung dan "
            "apa artinya dalam praktik."
        ),
    },
    "cy": {
        "name": "Welsh",
        "host_voice": "cy-GB-AledNeural",
        "guest_voice": "cy-GB-NiaNeural",
        "host_signoff": "Host: Diolch am wrando, welwn ni chi y tro nesaf!",
        "fallback_takeaway": (
            "Guest: Y peth pwysig yw sut mae'r syniadau hyn yn cysylltu a beth maen "
            "nhw'n ei olygu yn ymarferol."
        ),
    },
    # Serbian is written in both scripts, so the script follows the document's
    # (see _refine_code): 'sr' = Cyrillic, 'sr-latn' = Latin. Same native voices.
    "sr": {
        "name": "Serbian (Cyrillic script)",
        "host_voice": "sr-RS-NicholasNeural",
        "guest_voice": "sr-RS-SophieNeural",
        "host_signoff": "Host: Хвала што сте слушали, до следећег пута!",
        "fallback_takeaway": (
            "Guest: Најважније је како су ове идеје повезане и шта значе у пракси."
        ),
    },
    "sr-latn": {
        "name": "Serbian (Latin script)",
        "host_voice": "sr-RS-NicholasNeural",
        "guest_voice": "sr-RS-SophieNeural",
        "host_signoff": "Host: Hvala što ste slušali, do sledećeg puta!",
        "fallback_takeaway": (
            "Guest: Najvažnije je kako su ove ideje povezane i šta znače u praksi."
        ),
    },
    "hr": {
        "name": "Croatian",
        "host_voice": "hr-HR-SreckoNeural",
        "guest_voice": "hr-HR-GabrijelaNeural",
        "host_signoff": "Host: Hvala što ste slušali, do sljedećeg puta!",
        "fallback_takeaway": (
            "Guest: Najvažnije je kako su ove ideje povezane i što znače u praksi."
        ),
    },
    "mk": {
        "name": "Macedonian",
        "host_voice": "mk-MK-AleksandarNeural",
        "guest_voice": "mk-MK-MarijaNeural",
        "host_signoff": "Host: Ви благодариме што слушавте, до следниот пат!",
        "fallback_takeaway": (
            "Guest: Најважно е како овие идеи се поврзани и што значат во пракса."
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


# langdetect has no Serbian or Malay model: Serbian Cyrillic comes back as
# mk/bg/ru, Serbian Latin as hr/sl, and Malay as id. These marker sets tell them
# apart from the language langdetect picked. Cyrillic Serbian vs Macedonian is
# decided by letters unique to each alphabet; the Latin cases by common words
# that differ in spelling (ekavian vs ijekavian, Malay vs Indonesian vocabulary).
_SR_CYRL_LETTERS = set("ђћЂЋ")
_MK_CYRL_LETTERS = set("ќѓѕЌЃЅ")
_SR_LATN_WORDS = {
    "sledeće", "sledeći", "sledećeg", "reč", "reči", "rečima", "vreme", "pre",
    "posle", "deca", "dece", "dete", "lepo", "uvek", "ceo", "cela", "celog",
    "primer", "vek", "veka", "tokom", "takođe", "hiljada", "hiljade", "opština",
    "porodica", "porodice", "univerzitet", "nedelja", "nedelje", "hleb", "voz",
    "tačka", "muzika", "istorija", "istorije", "evropa", "ko", "šta", "svet",
    "sveta", "mleko", "reka", "reke", "mesto", "mesta",
}
_HR_WORDS = {
    "sljedeće", "sljedeći", "sljedećeg", "riječ", "riječi", "riječima", "vrijeme",
    "prije", "poslije", "djeca", "djece", "dijete", "lijepo", "uvijek", "cijeli",
    "cijela", "primjer", "stoljeće", "tijekom", "također", "tisuća", "općina",
    "obitelj", "obitelji", "sveučilište", "tjedan", "kruh", "vlak", "točka",
    "glazba", "povijest", "povijesti", "europa", "tko", "svijet", "svijeta",
    "mlijeko", "rijeka", "rijeke", "mjesto", "mjesta",
}
# Slovenian shares some ekavian spellings with Serbian ("mesto", "primer"), so a
# langdetect 'sl' result only becomes Serbian when these Slovenian words are rarer.
_SL_WORDS = {"tudi", "lahko", "zelo", "kot", "ki", "vendar", "oziroma", "torej", "bodo"}
_MS_WORDS = {
    "kerana", "sahaja", "selepas", "berbanding", "iaitu", "manakala", "baharu",
    "wang", "percuma", "bahawa", "dimulakan", "peratus", "bilion", "antarabangsa",
    "universiti", "polis", "sukan", "pejabat", "syarikat", "maklumat",
    "pembaharuan", "kakitangan",
}
_ID_WORDS = {
    "karena", "saja", "setelah", "uang", "gratis", "bahwa", "dimulai", "persen",
    "miliar", "internasional", "universitas", "polisi", "olahraga", "kantor",
    "perusahaan", "informasi", "pembaruan", "karyawan", "pemerintah", "yaitu",
    "bisa", "mencakup",
}


# Design-tool PDFs (Canva, InDesign tracking) often extract with a space between
# every letter: "T H E  F I L I P I N O  I N". langdetect only sees single
# letters there and calls plain English Welsh with ~100% confidence. A space
# between two single-character "words" is removed on lines that are mostly
# single characters, so "T H E  F I L I P I N O" reads "THE FILIPINO".
_SPACED_LETTER_GAP = re.compile(r"(?<=\b\w) (?=\w\b)")


def _unspace_letters(text: str) -> str:
    """Undo letter-spacing for language detection only (not for the LLM)."""
    lines = []
    for line in text.split("\n"):
        tokens = line.split()
        if len(tokens) >= 6 and sum(len(t) == 1 for t in tokens) / len(tokens) >= 0.6:
            line = " ".join(_SPACED_LETTER_GAP.sub("", line).split())
        lines.append(line)
    return "\n".join(lines)


# Detection looks at the start, middle and end of a document rather than only its
# opening, and a language wins only with a majority of those windows. One odd
# section (a French abstract on an English report, a garbled page, a bilingual
# cover) then can't decide the whole podcast's language. Docs too short for three
# independent windows use one window over the whole text.
_WINDOW_RAW_CHARS = 6000  # raw slice per window; letter-spaced text is ~2x longer
_WINDOW_CHARS = 3000      # what langdetect sees per window
_MULTI_WINDOW_MIN_CHARS = 4000


def _detection_slices(text: str) -> list[str]:
    """Raw start / middle / end slices (one slice for short docs)."""
    n = len(text)
    if n < _MULTI_WINDOW_MIN_CHARS:
        return [text]
    span = min(_WINDOW_RAW_CHARS, n // 3)
    mid = n // 2 - span // 2
    return [text[:span], text[mid:mid + span], text[n - span:]]


def _detection_samples(text: str) -> list[str]:
    """Windows langdetect sees: letter-spacing undone, up to 3000 chars each."""
    samples = [_unspace_letters(s)[:_WINDOW_CHARS] for s in _detection_slices(text)]
    return [s for s in samples if len(s.strip()) >= 30]


# English safety check, independent of langdetect. Calling an English document
# another language is the costly mistake (the whole podcast is unintelligible to
# the user); the reverse just falls back to English. Real English prose is ~20-35%
# these function words, every supported language measures 0-4%, and a foreign doc
# with a quarter English mixed in ~7% — so a sample at >= 15% is English, whatever
# langdetect says. Words that also exist in a supported language ("in", "is", "to",
# "for", "on", "or", "an", "at", "was", "will", "her", "die"...) are left out.
_ENGLISH_FUNCTION_WORDS = {
    "the", "of", "and", "that", "it", "with", "by", "this", "are", "from", "which",
    "but", "have", "they", "you", "we", "has", "their", "been", "were", "would",
    "there", "can", "more", "also", "these", "than", "not", "its", "our", "what",
    "when", "who", "how", "about", "into", "other", "such", "only", "some", "his",
    "she", "them", "then", "if", "one", "may", "should", "could", "because",
    "between", "through", "each", "those", "your",
}
_ENGLISH_SHARE_MIN = 0.15
_WORD_RE = re.compile(r"[^\W\d_]+")
_CJK_RE = re.compile(r"[぀-ヿ一-鿿가-힯]")


def _english_share(sample: str) -> float:
    """Fraction of words that are English function words (0 for < 20 words).

    Counts words in every script (CJK characters one each), so English quotes
    inside a Russian or Chinese document stay a small share.
    """
    words = _WORD_RE.findall(sample.lower())
    total = sum(len(_CJK_RE.findall(w)) or 1 for w in words)
    if total < 20:
        return 0.0
    return sum(w in _ENGLISH_FUNCTION_WORDS for w in words) / total


def _vote(text: str) -> tuple[str | None, list[str]]:
    """Detect each window and return (majority code or None, per-window codes).

    Raises if langdetect is unavailable or every window fails to detect.
    """
    from langdetect import detect, DetectorFactory

    codes = []
    for sample in _detection_samples(text):
        if _english_share(sample) >= _ENGLISH_SHARE_MIN:
            codes.append("en")
            continue
        DetectorFactory.seed = 0  # deterministic across runs
        try:
            raw = detect(sample).lower()
        except Exception:  # noqa: BLE001 — one undetectable window just doesn't vote
            continue
        code = _refine_code(raw, sample)
        # langdetect splits Chinese into zh-cn / zh-tw; they are one language here.
        codes.append("zh" if code.startswith("zh-") else code)
    if not codes:
        raise RuntimeError("no detectable text")
    best = max(set(codes), key=codes.count)
    return (best if codes.count(best) * 2 > len(codes) else None), codes


def _word_hits(text: str, words: set[str]) -> int:
    tokens = (t.strip(".,;:!?\"'()[]«»„“”—–-") for t in text.lower().split())
    return sum(1 for t in tokens if t in words)


def _refine_code(code: str, text: str) -> str:
    """Re-classify langdetect's guess for languages it can't detect (Serbian,
    Malay). Returns ``code`` unchanged for every other case."""
    if code in ("mk", "bg", "ru"):
        if sum(ch in _SR_CYRL_LETTERS for ch in text) > sum(ch in _MK_CYRL_LETTERS for ch in text):
            return "sr"
        return code
    if code in ("hr", "sl"):
        sr = _word_hits(text, _SR_LATN_WORDS)
        if sr > _word_hits(text, _HR_WORDS) and (code == "hr" or sr > _word_hits(text, _SL_WORDS)):
            return "sr-latn"
        return code
    if code == "id" and _word_hits(text, _MS_WORDS) > _word_hits(text, _ID_WORDS):
        return "ms"
    return code


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
        winner, codes = _vote(sample)
    except Exception as e:
        logger.warning(f"[lang] detection failed ({e}); defaulting to English")
        return "en"
    if winner is None:
        logger.info(f"[lang] windows disagree {codes} — using English")
        return "en"
    code = winner

    if code in LANGUAGE_PROFILES:
        logger.info(f"[lang] detected supported language '{code}' — native podcast")
        return code
    logger.info(f"[lang] detected '{code}' (no native support) — using English")
    return "en"


# ISO 639-1 → English name, covering langdetect's supported set. Used only for the
# admin notification label (detect_language_name), so it can show the document's
# TRUE language even when the podcast itself falls back to English.
_LANG_NAMES: dict[str, str] = {
    "af": "Afrikaans", "ar": "Arabic", "bg": "Bulgarian", "bn": "Bengali",
    "ca": "Catalan", "cs": "Czech", "cy": "Welsh", "da": "Danish", "de": "German",
    "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "gu": "Gujarati",
    "he": "Hebrew", "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian",
    "id": "Indonesian", "it": "Italian", "ja": "Japanese", "kn": "Kannada",
    "ko": "Korean", "lt": "Lithuanian", "lv": "Latvian", "mk": "Macedonian",
    "ml": "Malayalam", "mr": "Marathi", "ne": "Nepali", "nl": "Dutch",
    "no": "Norwegian", "pa": "Punjabi", "pl": "Polish", "pt": "Portuguese",
    "ro": "Romanian", "ru": "Russian", "sk": "Slovak", "sl": "Slovenian",
    "so": "Somali", "sq": "Albanian", "sv": "Swedish", "sw": "Swahili",
    "sr": "Serbian", "sr-latn": "Serbian (Latin)", "ms": "Malay",
    "ta": "Tamil", "te": "Telugu", "th": "Thai", "tl": "Tagalog",
    "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese",
    "zh-cn": "Chinese (Simplified)", "zh-tw": "Chinese (Traditional)",
    "zh": "Chinese",
}


def detect_language_name(text: str) -> str:
    """Human-readable language of a document, for admin notification emails.

    Unlike :func:`detect_language`, this is INDEPENDENT of MULTILINGUAL_ENABLED and
    of native-voice support — it reports the document's ACTUAL language (e.g.
    "German (de)") even when the podcast itself falls back to English, so feedback
    can be written in the user's language. Returns "Unknown" when detection isn't
    possible (too little text, detector unavailable).
    """
    sample = (text or "").strip()
    if len(sample) < 30:
        return "Unknown"
    try:
        winner, codes = _vote(sample)
    except Exception as e:  # noqa: BLE001 — label is best-effort, never fatal
        logger.warning(f"[lang] name detection failed ({e})")
        return "Unknown"

    def _label(raw: str) -> str:
        name = _LANG_NAMES.get(raw) or _LANG_NAMES.get(raw.split("-")[0])
        return f"{name} ({raw})" if name else raw

    if winner is None:
        # No majority — show every window's language so the admin can see why
        # the podcast fell back to English.
        return "Mixed: " + " / ".join(_label(c) for c in dict.fromkeys(codes))
    return _label(winner)


def detection_confidence(text: str) -> str:
    """How sure the language pick was, for the admin notification email.

    Uses the same windows and vote as :func:`detect_language`, so the row always
    describes the decision the podcast was actually made with. "⚠︎" marks the cases
    worth a quick listen: samples disagreed, or the text was letter-spaced (the
    pattern behind the English-read-as-Welsh bug). A wrong pick and the podcast it
    produces always "match" each other, so the input/output rows can't show this.
    """
    sample = (text or "").strip()
    if len(sample) < 30:
        return "Unknown (too little text)"
    try:
        winner, codes = _vote(sample)
    except Exception:  # noqa: BLE001 — label is best-effort, never fatal
        return "Unknown"

    n = len(codes)
    votes = ", ".join(codes)
    if n == 1:
        summary = "1 sample (short document)"
    elif winner is None:
        summary = f"⚠︎ no majority ({votes}) — English used"
    elif codes.count(winner) == n:
        summary = f"{n}/{n} samples agree"
    else:
        summary = f"⚠︎ {codes.count(winner)}/{n} samples agree ({votes})"
    if any(_unspace_letters(s) != s for s in _detection_slices(sample)):
        summary += " · ⚠︎ letter-spaced text fixed"
    return summary
