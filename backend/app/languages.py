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
import unicodedata

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
    # Norwegian = Bokmål voices (langdetect's 'no' also covers Nynorsk documents).
    "no": {
        "name": "Norwegian",
        "host_voice": "nb-NO-FinnNeural",
        "guest_voice": "nb-NO-PernilleNeural",
        "host_signoff": "Host: Takk for at du lyttet, vi ses i neste episode!",
        "fallback_takeaway": (
            "Guest: Det viktigste er hvordan disse ideene henger sammen, og hva de "
            "betyr i praksis."
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
    # Chinese is split by SCRIPT (see _cjk_code): Simplified (Mainland voices)
    # and Traditional (Taiwan voices), so a Traditional document is never
    # rewritten in Simplified characters, or the reverse.
    "zh": {
        "name": "Chinese (Simplified)",
        "host_voice": "zh-CN-YunxiNeural",
        "guest_voice": "zh-CN-XiaoxiaoNeural",
        "host_signoff": "Host: 感谢收听，我们下期再见！",
        "fallback_takeaway": (
            "Guest: 关键在于理解这些观点之间的联系，以及它们在实际中的意义。"
        ),
    },
    "zh-tw": {
        "name": "Chinese (Traditional)",
        "host_voice": "zh-TW-YunJheNeural",
        "guest_voice": "zh-TW-HsiaoChenNeural",
        "host_signoff": "Host: 感謝收聽，我們下期再見！",
        "fallback_takeaway": (
            "Guest: 關鍵在於理解這些觀點之間的聯繫，以及它們在實際中的意義。"
        ),
    },
    "ja": {
        "name": "Japanese",
        "host_voice": "ja-JP-KeitaNeural",
        "guest_voice": "ja-JP-NanamiNeural",
        "host_signoff": "Host: お聞きいただきありがとうございました。また次回お会いしましょう！",
        "fallback_takeaway": (
            "Guest: 大切なのは、これらの考えがどのようにつながり、実際に何を意味するのかということです。"
        ),
    },
    "ko": {
        "name": "Korean",
        "host_voice": "ko-KR-InJoonNeural",
        "guest_voice": "ko-KR-SunHiNeural",
        "host_signoff": "Host: 들어주셔서 감사합니다. 다음에 또 만나요!",
        "fallback_takeaway": (
            "Guest: 중요한 것은 이 아이디어들이 서로 어떻게 연결되고 실제로 어떤 "
            "의미를 갖는지입니다."
        ),
    },
    "fi": {
        "name": "Finnish",
        "host_voice": "fi-FI-HarriNeural",
        "guest_voice": "fi-FI-NooraNeural",
        "host_signoff": "Host: Kiitos kuuntelemisesta, kuullaan taas ensi kerralla!",
        "fallback_takeaway": (
            "Guest: Olennaista on, miten nämä ajatukset liittyvät toisiinsa ja mitä ne "
            "tarkoittavat käytännössä."
        ),
    },
    "et": {
        "name": "Estonian",
        "host_voice": "et-EE-KertNeural",
        "guest_voice": "et-EE-AnuNeural",
        "host_signoff": "Host: Aitäh kuulamast, kohtumiseni järgmisel korral!",
        "fallback_takeaway": (
            "Guest: Oluline on see, kuidas need mõtted omavahel seotud on ja mida need "
            "praktikas tähendavad."
        ),
    },
    # Azerbaijani: langdetect has no model for it; "ə" identifies it (see _refine_code).
    "az": {
        "name": "Azerbaijani",
        "host_voice": "az-AZ-BabekNeural",
        "guest_voice": "az-AZ-BanuNeural",
        "host_signoff": "Host: Dinlədiyiniz üçün təşəkkür edirik, növbəti dəfə görüşənədək!",
        "fallback_takeaway": (
            "Guest: Əsas məsələ bu fikirlərin bir-biri ilə necə bağlı olduğu və "
            "praktikada nə demək olduğudur."
        ),
    },
    "hu": {
        "name": "Hungarian",
        "host_voice": "hu-HU-TamasNeural",
        "guest_voice": "hu-HU-NoemiNeural",
        "host_signoff": "Host: Köszönjük, hogy meghallgattak, legközelebb találkozunk!",
        "fallback_takeaway": (
            "Guest: A lényeg az, hogy ezek a gondolatok hogyan kapcsolódnak "
            "egymáshoz, és mit jelentenek a gyakorlatban."
        ),
    },
    "cs": {
        "name": "Czech",
        "host_voice": "cs-CZ-AntoninNeural",
        "guest_voice": "cs-CZ-VlastaNeural",
        "host_signoff": "Host: Děkujeme za poslech, uslyšíme se příště!",
        "fallback_takeaway": (
            "Guest: Podstatné je, jak spolu tyto myšlenky souvisejí a co znamenají "
            "v praxi."
        ),
    },
    "sk": {
        "name": "Slovak",
        "host_voice": "sk-SK-LukasNeural",
        "guest_voice": "sk-SK-ViktoriaNeural",
        "host_signoff": "Host: Ďakujeme za počúvanie, dovidenia nabudúce!",
        "fallback_takeaway": (
            "Guest: Podstatné je, ako tieto myšlienky navzájom súvisia a čo znamenajú "
            "v praxi."
        ),
    },
    "pl": {
        "name": "Polish",
        "host_voice": "pl-PL-MarekNeural",
        "guest_voice": "pl-PL-ZofiaNeural",
        "host_signoff": "Host: Dziękujemy za wysłuchanie, do usłyszenia następnym razem!",
        "fallback_takeaway": (
            "Guest: Najważniejsze jest to, jak te idee łączą się ze sobą i co oznaczają "
            "w praktyce."
        ),
    },
    "sl": {
        "name": "Slovenian",
        "host_voice": "sl-SI-RokNeural",
        "guest_voice": "sl-SI-PetraNeural",
        "host_signoff": "Host: Hvala, ker ste poslušali, se slišimo prihodnjič!",
        "fallback_takeaway": (
            "Guest: Bistveno je, kako so te ideje povezane med seboj in kaj pomenijo "
            "v praksi."
        ),
    },
    "bg": {
        "name": "Bulgarian",
        "host_voice": "bg-BG-BorislavNeural",
        "guest_voice": "bg-BG-KalinaNeural",
        "host_signoff": "Host: Благодарим ви, че слушахте, до следващия път!",
        "fallback_takeaway": (
            "Guest: Най-важното е как тези идеи са свързани помежду си и какво "
            "означават на практика."
        ),
    },
    "uk": {
        "name": "Ukrainian",
        "host_voice": "uk-UA-OstapNeural",
        "guest_voice": "uk-UA-PolinaNeural",
        "host_signoff": "Host: Дякуємо, що слухали, до зустрічі в наступному випуску!",
        "fallback_takeaway": (
            "Guest: Головне — зрозуміти, як ці ідеї пов'язані між собою і що вони "
            "означають на практиці."
        ),
    },
    "tr": {
        "name": "Turkish",
        "host_voice": "tr-TR-AhmetNeural",
        "guest_voice": "tr-TR-EmelNeural",
        "host_signoff": "Host: Dinlediğiniz için teşekkürler, bir sonraki bölümde görüşmek üzere!",
        "fallback_takeaway": (
            "Guest: Önemli olan, bu fikirlerin birbirine nasıl bağlandığı ve pratikte "
            "ne anlama geldiği."
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
# Letters the Serbian and Macedonian alphabets don't have at all, but Russian,
# Ukrainian and Bulgarian use constantly. A text without them can only be one of
# those two; a text with them can't be either. Within each group, letters only
# one language uses decide when langdetect picks the wrong sibling.
_NOT_SR_MK_LETTERS = set("йъыьэщёяюєіїґЙЪЫЬЭЩЁЯЮЄІЇҐ")
_RU_LETTERS = set("ыэёЫЭЁ")
_UK_LETTERS = set("іїєґІЇЄҐ")
_BG_LETTERS = set("ъЪ")
# Serbian vs Macedonian function words, for sentences with no ђ/ћ/ќ/ѓ/ѕ at all
# (e.g. Serbian "је"/"су"/"у" vs Macedonian "е"/"во"/"со"/"ќе").
_SR_CYRL_WORDS = {"је", "су", "није", "у", "ово", "који", "које", "шта", "када", "веома", "између", "године", "после"}
_MK_CYRL_WORDS = {"е", "во", "со", "ќе", "кој", "кое", "сите", "многу", "денеска", "бидејќи", "кога", "нема", "ги", "го", "овој", "сум", "дека", "сепак", "зошто", "толку"}
# Bulgarian vs Russian (and vs Macedonian/Serbian when a short Bulgarian sentence
# happens to contain none of its tell-tale letters): "в" (in) and "ще"/"че" are
# Bulgarian; Macedonian says "во", Serbian "у", Russian "что"/"это".
_BG_CYRL_WORDS = {"в", "ще", "че", "това", "които", "който", "която", "беше", "защо", "също", "според"}
_RU_CYRL_WORDS = {"что", "это", "был", "была", "было", "который", "которые", "также", "почему", "для", "его"}


# Hungarian / Turkish / Finnish-Estonian / Azerbaijani each use letters the others
# never do: ő ű / ğ ı / ä õ / ə.
_HU_LETTERS = set("őűŐŰ")
_TR_LETTERS = set("ğıĞİ")
_FI_ET_LETTERS = set("äõÄÕ")
_AZ_LETTERS = set("əƏ")
# For sentences that happen to contain none of those letters.
_HU_FUNCTION_WORDS = {"és", "az", "hogy", "egy", "nem", "azt", "ez", "egyes", "miért", "olyan", "vagy", "csak", "már", "még", "pedig", "amely", "szerint", "között", "után", "neki"}
_FI_ET_FUNCTION_WORDS = {"ja", "on", "ei", "että", "se", "ovat", "kuin", "mutta", "myös", "tai", "joka", "kun", "niin", "et", "see", "ka", "kui", "aga", "või", "mis", "nii", "oma", "miks", "kuidas"}
_TR_FUNCTION_WORDS = {"ve", "bir", "bu", "için", "ile", "çok", "daha", "olarak", "gibi", "değil", "olan"}
# Finnish vs Estonian (both supported): Estonian uses "õ", Finnish never does;
# words that exist in only one of them ("että"/"et", "kuin"/"kui", "se"/"see").
_ET_LETTERS = set("õÕüÜ")  # Estonian writes "ü" where Finnish writes "y"
_FI_LETTERS = set("yY")
# Hindi vs Marathi vs Nepali share Devanagari. Marathi uses "ळ", which Hindi never
# does; each also has its own everyday words ("है"/"आहे"/"छ" = is).
_MR_LETTERS = set("ळ")
_HI_DEVA_WORDS = {"है", "हैं", "और", "में", "से", "यह", "था", "थी", "थे", "लिए", "करने", "किया"}
_MR_DEVA_WORDS = {"आहे", "आहेत", "आणि", "होते", "होती", "करण्यात", "म्हणून", "त्या", "हा", "ही"}
_NE_DEVA_WORDS = {"छ", "छन्", "र", "हुनेछ", "लाई", "ले", "भएको", "गरेको", "पनि", "हो", "गर्न"}
_FI_ONLY_WORDS = {
    "että", "ovat", "kuin", "mutta", "myös", "tai", "joka", "kun", "niin", "hän", "se",
    "tämä", "ole", "olla", "noin", "mukaan", "kanssa", "vain", "jo", "nyt", "sekä",
    "eli", "jos", "koska", "ennen", "jälkeen", "aikana", "paljon", "hyvin",
}
_ET_ONLY_WORDS = {
    "et", "see", "ka", "kui", "aga", "või", "mis", "nii", "oma", "miks", "kuidas",
    "ning", "seda", "umbes", "järgi", "koos", "ainult", "juba", "nüüd", "sest",
    "pärast", "ajal", "palju", "hästi",
}

# Chinese / Japanese / Korean are decided by WRITING SYSTEM, not statistics:
# Hangul is Korean-only, Kana is Japanese-only (and in every normal Japanese
# sentence), and Chinese is Han characters with neither. langdetect alone calls
# Traditional Chinese Korean, so for CJK text it is not consulted at all.
_HANGUL_RE = re.compile("[가-힣ᄀ-ᇿ㄰-㆏]")
# Kana, minus U+30FB "・" which Chinese also uses between parts of foreign names.
_KANA_RE = re.compile("[぀-ゟ゠-ヺー-ヿㇰ-ㇿｦ-ﾟ]")
_HAN_RE = re.compile("[㐀-䶿一-鿿豈-﫿]")
_CJK_CODES = ("zh", "zh-cn", "zh-tw", "ja", "ko")
# Simplified vs Traditional Chinese: the same Han script, but these very common
# characters are written differently (position i in one string is the other's
# counterpart). Characters both standards share (里, 后, 台, 面...) are left out.
_ZH_SIMPLIFIED = (
    "个们这来时为说国会对发过还进动现么样经开问点学关题从间头实种机长业与东车门见让认应"
    "产气书体万专医药疗术断诊检验证脑肠胆脏伤节线织组细结级处变压静脉华语话读写听买卖钱"
    "银铁电网页图报纸场广区县乡农员师爱亲观历岁难欢乐劳务统计设议论讲课试选达运远边连适"
    "递际陆阳阴险鸡鱼鸟马龙风云阵无刚别则刘创显质负贵费资贸赛贡购赶轻较辅输办励劝势单卫"
    "厂厅双号叶复"
)
_ZH_TRADITIONAL = (
    "個們這來時為說國會對發過還進動現麼樣經開問點學關題從間頭實種機長業與東車門見讓認應"
    "產氣書體萬專醫藥療術斷診檢驗證腦腸膽臟傷節線織組細結級處變壓靜脈華語話讀寫聽買賣錢"
    "銀鐵電網頁圖報紙場廣區縣鄉農員師愛親觀歷歲難歡樂勞務統計設議論講課試選達運遠邊連適"
    "遞際陸陽陰險雞魚鳥馬龍風雲陣無剛別則劉創顯質負貴費資貿賽貢購趕輕較輔輸辦勵勸勢單衛"
    "廠廳雙號葉復"
)
_ZH_SIMPLIFIED_SET = set(_ZH_SIMPLIFIED) - set(_ZH_TRADITIONAL)
_ZH_TRADITIONAL_SET = set(_ZH_TRADITIONAL) - set(_ZH_SIMPLIFIED)


def _cjk_code(sample: str) -> str | None:
    """'zh' / 'ja' / 'ko' for text that is mostly CJK characters, 'cjk-mixed' when
    the scripts don't clearly fit one language (so it falls back to English), and
    None for text that isn't mostly CJK."""
    hangul = len(_HANGUL_RE.findall(sample))
    kana = len(_KANA_RE.findall(sample))
    han = len(_HAN_RE.findall(sample))
    cjk = hangul + kana + han
    if cjk < 20:
        return None
    # One CJK character carries about as much as 3-4 Latin letters, so weigh it 3x
    # when deciding whether the text is mostly CJK (a Chinese doc full of English
    # terms like "Python" or "API" still is).
    latin = sum(ch.isalpha() for ch in sample) - cjk
    if cjk * 3 < latin:
        # Substantial CJK in a mostly-Latin text (~a third or more by weight):
        # never let langdetect put a Latin-script label (e.g. Vietnamese) on it.
        # A few CJK words in, say, French prose are left to normal detection.
        return "cjk-mixed" if cjk * 10 >= latin else None
    if kana >= max(5, 0.02 * cjk):
        return "ja" if hangul <= 0.01 * cjk else "cjk-mixed"
    if hangul >= 0.6 * cjk:
        return "ko"
    if hangul <= 0.01 * cjk:
        # Chinese: Traditional only when its distinct characters clearly
        # outnumber the Simplified ones; Simplified otherwise (the far larger
        # audience, and the safe default for text with few distinct characters).
        trad = sum(ch in _ZH_TRADITIONAL_SET for ch in sample)
        simp = sum(ch in _ZH_SIMPLIFIED_SET for ch in sample)
        return "zh-tw" if trad >= 2 and trad > 3 * simp else "zh"
    return "cjk-mixed"


def _dominant(scores: dict[str, int]) -> str | None:
    """The key whose count is at least 2 and over 3x every other, else None."""
    best = max(scores, key=scores.get)
    rest = max((v for k, v in scores.items() if k != best), default=0)
    return best if scores[best] >= 2 and scores[best] > 3 * rest else None
# Czech and Slovak are both supported and very close, so a wrong call would give
# the neighbouring language instead of falling back to English. Each has letters
# the other doesn't use: an independent check on top of langdetect.
_CS_LETTERS = set("ěřůĚŘŮ")
_SK_LETTERS = set("äľĺŕôÄĽĹŔÔ")
_PL_LETTERS = set("ąęłśźżńĄĘŁŚŹŻŃ")
# Function words for Czech / Slovak / Polish text written WITHOUT diacritics
# (matched accent-insensitively), when the letters above are missing. Words that
# collide once accents are dropped ("jak", "jako", "byl", "nie", "ktory", "moze",
# "tez", "jednak") are left out.
_CS_FUNCTION_WORDS = {"se", "jsou", "pro", "nebo", "ktery", "ktera", "ktere", "podle", "take", "neni", "ve", "jsme", "jste", "tedy"}
_SK_FUNCTION_WORDS = {"sa", "su", "ako", "pre", "bol", "bola", "bolo", "alebo", "podla", "tiez", "vo", "sme", "ste", "teda"}
_PL_FUNCTION_WORDS = {"jest", "sie", "oraz", "przez", "przy", "dla", "juz", "tylko", "bardzo", "gdy"}
# Danish / Norwegian (both supported) vs Swedish: Swedish writes ä/ö where the
# other two write æ/ø. Each word list holds words ONLY that language uses —
# shared ones ("blir", "av", "nu", "efter", "mig", "blev"...) would flip siblings.
_SV_LETTERS = set("äöÄÖ")
_SV_WORDS = {"och", "att", "är", "inte", "vad", "något", "mycket", "också", "eller", "när", "från", "utan", "sjukhuset", "läkarna"}
_DA_WORDS = {
    "af", "hvad", "noget", "nogle", "meget", "bliver", "sådan", "hospitalet", "lægerne",
    "frem", "næste", "siger", "penge", "høj", "indlagt", "hovedpine", "udskrev", "mere",
}
_NO_WORDS = {
    "hva", "etter", "noe", "noen", "meg", "deg", "seg", "ble", "slik", "mye", "sykehuset",
    "legene", "ikkje", "fram", "neste", "sier", "trengs", "penger", "høy", "innlagt",
    "hodepine", "ettermiddagen", "regjeringen",
}
# Arabic / Persian / Urdu (all supported): Urdu-only letters, Persian letters
# (also used by Urdu, so checked second) and Persian "ی" vs Arabic "ي", Arabic "ة".
_UR_LETTERS = set("ٹڈڑںے")
_FA_LETTERS = set("پچژگی")
_AR_LETTERS = set("ةي")
# Slovenian vs Croatian: Slovenian never uses ć/đ, and their everyday function
# words differ ("in"/"i" = and, "so"/"su" = are, "v"/"u" = in, "ki"/"koji" = which).
_HR_LETTERS = set("ćđĆĐ")
_SL_FUNCTION_WORDS = {
    "in", "so", "bo", "bodo", "ki", "kot", "tudi", "zelo", "pa", "ni", "v", "z",
    "zaradi", "predvsem", "lahko", "zakaj", "vendar", "oziroma", "torej",
    "odstotkov", "odstotka", "odstotke",
}
# ("će" is left out: without diacritics it reads like Slovenian "če" = if.)
_HR_FUNCTION_WORDS = {"i", "su", "nije", "ali", "što", "koji", "koja", "koje", "u"}
_SR_LATN_WORDS = {
    "sledeće", "sledeći", "sledećeg", "reč", "reči", "rečima", "vreme", "pre",
    "posle", "deca", "dece", "dete", "lepo", "uvek", "ceo", "cela", "celog",
    "primer", "vek", "veka", "tokom", "takođe", "hiljada", "hiljade", "opština",
    "porodica", "porodice", "univerzitet", "nedelja", "nedelje", "hleb", "voz",
    "tačka", "muzika", "istorija", "istorije", "evropa", "ko", "šta", "svet",
    "sveta", "mleko", "reka", "reke", "mesto", "mesta",
    # Vocabulary that differs outright (Serbian / Croatian): uticaj/utjecaj,
    # kompanija/tvrtka, procenat/posto, lekar/liječnik, inostranstvo/inozemstvo...
    "uticaj", "uticaja", "uticaju", "kompanija", "kompanije", "kompaniji", "procenat",
    "procenata", "procenta", "lekar", "lekari", "lekara", "lekaru", "inostranstvo",
    "inostranstvu", "inostranstva", "bezbednost", "bezbednosti", "saradnja",
    "saradnje", "saradnji", "hiljadu", "sedmica", "sedmice", "celu", "celom",
    "funkcioniše", "funkcionišu", "vazduh", "fabrika", "pozorište",
}
_HR_WORDS = {
    "sljedeće", "sljedeći", "sljedećeg", "riječ", "riječi", "riječima", "vrijeme",
    "prije", "poslije", "djeca", "djece", "dijete", "lijepo", "uvijek", "cijeli",
    "cijela", "primjer", "stoljeće", "tijekom", "također", "tisuća", "općina",
    "obitelj", "obitelji", "sveučilište", "tjedan", "kruh", "vlak", "točka",
    "glazba", "povijest", "povijesti", "europa", "tko", "svijet", "svijeta",
    "mlijeko", "rijeka", "rijeke", "mjesto", "mjesta",
    "utjecaj", "utjecaja", "utjecaju", "tvrtka", "tvrtke", "tvrtki", "tvrtku", "posto",
    "postotak", "postotaka", "liječnik", "liječnici", "liječnika", "liječniku",
    "inozemstvo", "inozemstvu", "inozemstva", "sigurnost", "sigurnosti", "suradnja",
    "suradnje", "suradnji", "tisuću", "cijelu", "cijelom", "funkcionira",
    "funkcioniraju", "zrak", "tvornica", "kazalište", "srijeda", "srijedu",
    "poslijepodne", "mjestimice", "stupnjeva",
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
# On such a line every single space is a letter gap and the wider gaps are word
# breaks. Removing single spaces (not \w-based) works for every script, including
# Devanagari, whose vowel signs aren't regex "word characters".
_SINGLE_SPACE = re.compile(r"(?<! ) (?! )")


def _unspace_letters(text: str) -> str:
    """Undo letter-spacing for language detection only (not for the LLM)."""
    lines = []
    for line in text.split("\n"):
        tokens = line.split()
        if len(tokens) >= 6 and sum(len(t) == 1 for t in tokens) / len(tokens) >= 0.6:
            line = " ".join(_SINGLE_SPACE.sub("", line).split())
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


_MIN_DISTINCT_WORDS = 12


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
        cjk = _cjk_code(sample)
        if cjk:
            codes.append(cjk)
            continue
        # Too little real content to tell close languages apart (a looping OCR
        # transcript, a snippet): a statistical guess here picked neighbours like
        # Bulgarian for Macedonian or Danish for Swedish. Fall back to English.
        if len(set(sample.lower().split())) < _MIN_DISTINCT_WORDS:
            codes.append("und")
            continue
        # langdetect misreads ALL-CAPS text (uppercase Polish/Czech/Finnish came
        # out German). Give it lowercase; the letter checks still see the original.
        cased = [ch for ch in sample if ch.isalpha() and ch.lower() != ch.upper()]
        probe = sample.lower() if cased and sum(ch.isupper() for ch in cased) * 2 > len(cased) else sample
        DetectorFactory.seed = 0  # deterministic across runs
        try:
            raw = detect(probe).lower()
        except Exception:  # noqa: BLE001 — one undetectable window just doesn't vote
            continue
        code = _refine_code(raw, sample)
        # Simplified Chinese's profile key is "zh"; Traditional keeps "zh-tw".
        codes.append("zh" if code == "zh-cn" else code)
    if not codes:
        raise RuntimeError("no detectable text")
    best = max(set(codes), key=codes.count)
    return (best if codes.count(best) * 2 > len(codes) else None), codes


_LETTER_RUN_RE = re.compile(r"[^\W\d_]+")


def _letter_words(s: str) -> list[str]:
    """Runs of letters only: numbering like "②" or "①" (Unicode "numbers" that
    regex \w still matches) and punctuation split words instead of gluing on."""
    return "".join(ch if ch.isalpha() else " " for ch in s).split()
# Devanagari words include vowel signs, which aren't regex "word characters".
_DEVANAGARI_RUN_RE = re.compile("[\u0900-\u0963\u0970-\u097f]+")
_FOLDED_SETS: dict[int, set[str]] = {}


def _fold(s: str) -> str:
    """Lowercase and drop diacritics ("Rečima" -> "recima")."""
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _word_hits(text: str, words: set[str], fold: bool = False) -> int:
    """How many words of ``text`` are in ``words``.

    Words are runs of letters, so numbering, arrows and years around them (mind
    maps, slides: "①Nije", "objasniti（2012）") don't hide them. ``fold`` matches
    accent-insensitively, for lanes where text may come without diacritics
    (Czech "vzdelavani", Serbian "recima").
    """
    if any("\u0900" <= ch <= "\u097f" for w in words for ch in w[:1]):
        return sum(1 for t in _DEVANAGARI_RUN_RE.findall(text) if t in words)
    if fold:
        folded = _FOLDED_SETS.get(id(words))
        if folded is None:
            folded = _FOLDED_SETS[id(words)] = {_fold(w) for w in words}
        return sum(1 for t in _letter_words(_fold(text)) if t in folded)
    return sum(1 for t in _letter_words(text.lower()) if t in words)



def _refine_code(code: str, text: str) -> str:
    """Re-classify langdetect's guess for languages it can't detect (Serbian,
    Malay), and arbitrate between close supported neighbours (Czech / Slovak /
    Polish, Slovenian / Croatian, Serbian / Macedonian / Bulgarian / Russian /
    Ukrainian) by letters or function words only one of them uses. Returns
    ``code`` unchanged for every other case."""
    if code in ("hi", "mr", "ne"):
        # Only Hindi is supported: Marathi/Nepali misread as Hindi would get a
        # Hindi podcast, so their own letters/words move them back (to English).
        return _dominant({
            "hi": _word_hits(text, _HI_DEVA_WORDS),
            "mr": sum(ch in _MR_LETTERS for ch in text) + _word_hits(text, _MR_DEVA_WORDS),
            "ne": _word_hits(text, _NE_DEVA_WORDS),
        }) or code
    if code in _CJK_CODES:
        # A CJK label on text that isn't mostly CJK characters has no evidence
        # behind it (CJK text never reaches langdetect, see _vote).
        return _cjk_code(text) or "und"
    if code in ("cs", "sk", "pl"):
        # Czech / Slovak / Polish each use letters the other two don't; ő/ű
        # catches Hungarian misread as one of them.
        scores = {
            "cs": sum(ch in _CS_LETTERS for ch in text) + _word_hits(text, _CS_FUNCTION_WORDS, fold=True),
            "sk": sum(ch in _SK_LETTERS for ch in text) + _word_hits(text, _SK_FUNCTION_WORDS, fold=True),
            "pl": sum(ch in _PL_LETTERS for ch in text) + _word_hits(text, _PL_FUNCTION_WORDS, fold=True),
            "hu": sum(ch in _HU_LETTERS for ch in text) + _word_hits(text, _HU_FUNCTION_WORDS),
        }
        best = _dominant(scores)
        if best:
            return best
        # Czech vs Slovak with no evidence either way (e.g. text without
        # diacritics or function words): langdetect is guessing between two
        # supported siblings, so don't trust it.
        if code in ("cs", "sk") and scores["cs"] == scores["sk"] == 0:
            return "und"
        return code
    if code in ("da", "no", "sv"):
        return _dominant({
            "sv": sum(ch in _SV_LETTERS for ch in text) + _word_hits(text, _SV_WORDS),
            "da": _word_hits(text, _DA_WORDS),
            "no": _word_hits(text, _NO_WORDS),
        }) or code
    if code in ("ar", "fa", "ur"):
        if sum(ch in _UR_LETTERS for ch in text) >= 2:
            return "ur"  # Persian and Arabic never use these
        return _dominant({
            "fa": sum(ch in _FA_LETTERS for ch in text),
            "ar": sum(ch in _AR_LETTERS for ch in text),
        }) or code
    if code in ("hu", "tr", "fi", "et", "az"):
        # Azerbaijani shares Turkish's ğ/ı, but "ə" alone is decisive: Turkish
        # never uses it (Azerbaijani is unsupported, so this means English).
        if sum(ch in _AZ_LETTERS for ch in text) >= 2:
            return "az"
        best = _dominant({
            "hu": sum(ch in _HU_LETTERS for ch in text) + _word_hits(text, _HU_FUNCTION_WORDS),
            "tr": sum(ch in _TR_LETTERS for ch in text) + _word_hits(text, _TR_FUNCTION_WORDS),
            "fi": sum(ch in _FI_ET_LETTERS for ch in text) + _word_hits(text, _FI_ET_FUNCTION_WORDS),
        })
        if best == "fi":
            # Finnic: tell Finnish from Estonian. If neither clearly wins, the
            # text is still known to be one of the two, so trust langdetect only
            # when it picked one of them; otherwise undetermined (English).
            return _dominant({
                "fi": sum(ch in _FI_LETTERS for ch in text) + _word_hits(text, _FI_ONLY_WORDS),
                "et": sum(ch in _ET_LETTERS for ch in text) + _word_hits(text, _ET_ONLY_WORDS),
            }) or (code if code in ("fi", "et") else "und")
        return best or code
    if code in ("mk", "bg", "ru", "uk"):
        if sum(ch in _NOT_SR_MK_LETTERS for ch in text) < 3:
            # Written in the Serbian/Macedonian alphabet: decide between those
            # two, first by their unique letters, then by function words.
            sr = sum(ch in _SR_CYRL_LETTERS for ch in text)
            mk = sum(ch in _MK_CYRL_LETTERS for ch in text)
            if sr == mk:
                sr, mk = _word_hits(text, _SR_CYRL_WORDS), _word_hits(text, _MK_CYRL_WORDS)
            if sr > mk:
                return "sr"
            if mk > sr:
                return "mk"
            # Neither: a short Bulgarian sentence can also look like this.
            if code in ("mk", "bg") and _dominant({"bg": _word_hits(text, _BG_CYRL_WORDS), "mk": mk}) == "bg":
                return "bg"
            return code
        # Russian / Ukrainian / Bulgarian alphabet: each has letters the other two
        # don't (ы э ё / і ї є ґ / ъ).
        best = _dominant({
            "ru": sum(ch in _RU_LETTERS for ch in text),
            "uk": sum(ch in _UK_LETTERS for ch in text),
            "bg": sum(ch in _BG_LETTERS for ch in text),
        })
        if best:
            return best
        # No decisive letters (e.g. a Bulgarian sentence without "ъ"): function words.
        best = _dominant({
            "bg": _word_hits(text, _BG_CYRL_WORDS),
            "ru": _word_hits(text, _RU_CYRL_WORDS),
        })
        if best:
            return best
        # Macedonian can't contain these letters at all; Bulgarian is its nearest.
        return "bg" if code == "mk" else code
    if code in ("hr", "sl"):
        hr_f = _word_hits(text, _HR_FUNCTION_WORDS, fold=True) + sum(ch in _HR_LETTERS for ch in text)
        sl_f = _word_hits(text, _SL_FUNCTION_WORDS, fold=True)
        code = _dominant({"hr": hr_f, "sl": sl_f}) or code
        sr = _word_hits(text, _SR_LATN_WORDS, fold=True)
        hr = _word_hits(text, _HR_WORDS, fold=True)
        if sr > hr and (code == "hr" or sr > _word_hits(text, _SL_WORDS, fold=True)):
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
    "zh": "Chinese (Simplified)",
    "cjk-mixed": "Mixed Chinese/Japanese/Korean", "und": "Undetermined",
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


def expected_language_label(text: str) -> str:
    """The language the podcast was SUPPOSED to be in, e.g. "Turkish (tr)".

    The pipeline's own decision (:func:`detect_language` + profile), so it is
    English for English and for every unsupported language. The admin email checks
    the generated script against this rather than against the input language.
    """
    code = detect_language(text)
    return f"{get_language_profile(code)['name']} ({code})"


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
