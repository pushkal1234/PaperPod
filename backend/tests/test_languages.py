"""Regression tests for document language detection (app.languages).

A wrong detection writes the whole podcast in the wrong language (an English PDF
once came out as a Welsh podcast), so every supported language, the tricky
English inputs that fooled the detector before, and mixed-language documents
are pinned here. Adding a language to LANGUAGE_PROFILES without a sample below
fails ``test_every_profile_has_a_sample``.

Needs ``langdetect`` (in requirements.txt). Run from the ``backend`` directory:

    ./venv/bin/python -m unittest discover -s tests
"""

import unittest

try:
    import langdetect  # noqa: F401
except ImportError as e:  # pragma: no cover - environment problem, not a test failure
    raise ImportError(
        "test_languages needs langdetect: ./venv/bin/pip install -r requirements.txt"
    ) from e

from app import languages
from app.config import settings
from app.languages import LANGUAGE_PROFILES, detect_language, detect_language_name


# --------------------------------------------------------------------------- #
# Samples: one short native paragraph per supported language
# --------------------------------------------------------------------------- #
SAMPLES = {
    "de": "Die Bundesregierung hat heute ein neues Bildungsgesetz beschlossen. Nach Angaben der Ministerin beginnt die Reform im nächsten Jahr und umfasst alle Grundschulen des Landes. Die Lehrkräfte begrüßen den Plan, fordern aber mehr Geld.",
    "fr": "Le gouvernement a adopté aujourd'hui une nouvelle loi sur l'éducation. Selon le ministre, la réforme commencera l'année prochaine et concernera toutes les écoles primaires du pays.",
    "el": "Η κυβέρνηση ενέκρινε σήμερα έναν νέο νόμο για την εκπαίδευση. Σύμφωνα με τον υπουργό, η μεταρρύθμιση θα ξεκινήσει τον επόμενο χρόνο και θα αφορά όλα τα δημοτικά σχολεία της χώρας.",
    "es": "El gobierno aprobó hoy una nueva ley de educación. Según el ministro, la reforma comenzará el próximo año y abarcará todas las escuelas primarias del país.",
    "pt": "O governo aprovou hoje uma nova lei de educação. Segundo o ministro, a reforma começará no próximo ano e abrangerá todas as escolas primárias do país.",
    "it": "Il governo ha approvato oggi una nuova legge sull'istruzione. Secondo il ministro, la riforma inizierà il prossimo anno e riguarderà tutte le scuole primarie del paese.",
    "hi": "सरकार ने आज शिक्षा पर एक नया कानून पारित किया। मंत्री के अनुसार, यह सुधार अगले साल शुरू होगा और देश के सभी प्राथमिक विद्यालयों को शामिल करेगा।",
    "vi": "Chính phủ hôm nay đã thông qua một luật giáo dục mới. Theo bộ trưởng, cải cách sẽ bắt đầu vào năm tới và áp dụng cho tất cả các trường tiểu học trong cả nước.",
    "da": "Regeringen har i dag vedtaget en ny lov om uddannelse. Ifølge ministeren begynder reformen næste år og omfatter alle landets folkeskoler.",
    "no": "Regjeringen la i dag fram en ny lov om utdanning. Ifølge statsråden skal reformen starte neste år og omfatte alle barneskoler i landet. Lærerne er positive til planen, men sier at det trengs mer penger.",
    "fa": "دولت امروز قانون جدیدی درباره آموزش تصویب کرد. به گفته وزیر، این اصلاحات از سال آینده آغاز می‌شود و همه مدارس ابتدایی کشور را در بر می‌گیرد.",
    "ar": "اعتمدت الحكومة اليوم قانونًا جديدًا للتعليم. ووفقًا للوزير، ستبدأ الإصلاحات العام المقبل وستشمل جميع المدارس الابتدائية.",
    "ur": "حکومت نے آج تعلیم کے بارے میں ایک نیا قانون منظور کیا۔ وزیر کے مطابق یہ اصلاحات اگلے سال شروع ہوں گی اور ملک کے تمام پرائمری اسکولوں پر لاگو ہوں گی۔",
    "ru": "Правительство России сегодня приняло новый закон об образовании. По словам министра, реформа начнётся в следующем году и охватит все начальные школы. Ученики будут иметь больше уроков информатики.",
    "nl": "De regering heeft vandaag een nieuwe onderwijswet aangenomen. Volgens de minister begint de hervorming volgend jaar en geldt deze voor alle basisscholen in het land.",
    "zh": "政府今天通过了一项新的教育法。部长表示，改革将于明年开始，并覆盖全国所有小学。教师们欢迎这项计划，但表示需要更多资金。",
    "cs": "Vláda dnes schválila nový zákon o vzdělávání. Podle ministra začne reforma příští rok a bude se týkat všech základních škol v zemi. Učitelé plán vítají, ale říkají, že je potřeba více peněz.",
    "sk": "Vláda dnes schválila nový zákon o vzdelávaní. Podľa ministra sa reforma začne budúci rok a bude sa týkať všetkých základných škôl v krajine. Učitelia plán vítajú, ale hovoria, že je potrebných viac peňazí.",
    "pl": "Rząd przyjął dzisiaj nową ustawę o edukacji. Według ministra reforma rozpocznie się w przyszłym roku i obejmie wszystkie szkoły podstawowe w kraju.",
    "sl": "Vlada je danes sprejela nov zakon o izobraževanju. Po besedah ministra se bo reforma začela prihodnje leto in bo zajela vse osnovne šole v državi.",
    "bg": "Правителството днес прие нов закон за образованието. Според министъра реформата ще започне догодина и ще обхване всички основни училища в страната.",
    "uk": "Уряд України сьогодні ухвалив новий закон про освіту. За словами міністра, реформа розпочнеться наступного року і охопить усі початкові школи країни. Вчителі вітають цей план, але кажуть, що потрібно більше коштів.",
    "tr": "Hükümet bugün eğitimle ilgili yeni bir yasa kabul etti. Bakana göre reform gelecek yıl başlayacak ve ülkedeki tüm ilkokulları kapsayacak. Öğretmenler planı memnuniyetle karşıladı ancak daha fazla kaynak gerektiğini söyledi.",
    "lt": "Lietuvos Vyriausybė šiandien patvirtino naują švietimo įstatymą. Pasak ministro, reforma prasidės kitais metais ir apims visas pagrindines mokyklas. Mokiniai turės daugiau informatikos pamokų, o mokytojai dalyvaus specialiuose mokymuose.",
    "ms": "Kerajaan Malaysia hari ini telah meluluskan undang-undang pendidikan yang baharu. Menurut menteri, pembaharuan itu akan bermula tahun depan dan melibatkan semua sekolah rendah. Murid akan mempunyai lebih banyak kelas teknologi maklumat kerana ia penting untuk masa depan, manakala guru-guru akan menjalani latihan khas selepas cuti sekolah.",
    "id": "Pemerintah Indonesia hari ini telah mengesahkan undang-undang pendidikan yang baru. Menurut menteri, reformasi itu akan dimulai tahun depan dan mencakup semua sekolah dasar. Siswa akan mendapat lebih banyak pelajaran teknologi informasi karena hal itu penting untuk masa depan, sedangkan para guru akan mengikuti pelatihan khusus setelah libur sekolah.",
    "cy": "Mae Llywodraeth Cymru wedi cyhoeddi cynllun newydd heddiw i wella addysg yn ysgolion cynradd y wlad. Yn ôl y gweinidog, bydd y newidiadau yn dechrau y flwyddyn nesaf a bydd pob plentyn yn cael mwy o wersi technoleg. Mae'r athrawon yn croesawu'r cynllun ond maen nhw'n dweud bod angen mwy o arian.",
    "sr": "Влада Србије је данас усвојила нови закон о образовању. Према речима министра, реформа ће почети следеће године и обухватиће све основне школе. Ђаци ће имати више часова информатике, а наставници ће проћи посебну обуку. Опозиција сматра да је закон донет пребрзо и да није било довољно јавне расправе.",
    "sr-latn": "Vlada Srbije je danas usvojila novi zakon o obrazovanju. Prema rečima ministra, reforma će početi sledeće godine i obuhvatiće sve osnovne škole. Đaci će imati više časova informatike, a nastavnici će proći posebnu obuku. Opozicija smatra da je zakon donet prebrzo i da nije bilo dovoljno javne rasprave o tome šta deca zaista treba da uče.",
    "hr": "Vlada Republike Hrvatske danas je usvojila novi zakon o obrazovanju. Prema riječima ministra, reforma će započeti sljedeće godine i obuhvatit će sve osnovne škole. Učenici će imati više sati informatike, a nastavnici će proći posebnu obuku. Oporba smatra da je zakon donesen prebrzo i da nije bilo dovoljno javne rasprave o tome što djeca zaista trebaju učiti.",
    "mk": "Владата на Северна Македонија денеска усвои нов закон за образование. Според зборовите на министерот, реформата ќе започне следната година и ќе ги опфати сите основни училишта. Учениците ќе имаат повеќе часови по информатика, а наставниците ќе поминат посебна обука.",
}

ENGLISH = (
    "The government announced a new education plan today to improve primary schools "
    "across the country. According to the minister, the changes will begin next year "
    "and every child will receive more technology lessons. Teachers welcomed the plan "
    "but said more funding is needed. "
)
WORKPLACE = (
    "Filipino employees are often described as responsible, dependable and hardworking. "
    "These values carry into the workplace, where respect for elders, loyalty to the "
    "team and a strong sense of family shape how people work together every day. "
)
# Unsupported languages that look like supported ones: must stay English.
ROMANIAN = "Guvernul a adoptat astăzi o nouă lege a educației. Potrivit ministrului, reforma va începe anul viitor și va cuprinde toate școlile primare din țară."
HUNGARIAN = "A kormány ma új oktatási törvényt fogadott el. A miniszter szerint a reform jövőre kezdődik, és az ország összes általános iskolájára kiterjed."

# Close Slavic neighbours, all supported: a mix-up gives the neighbouring language
# instead of an English fallback. Six parallel texts each (same topics, so shared
# vocabulary), checked one sentence, three sentences, long and letter-spaced.
SLAVIC = {
    "pl": [
        "Rząd przyjął dzisiaj nową ustawę o edukacji. Według ministra reforma rozpocznie się w przyszłym roku i obejmie wszystkie szkoły podstawowe w kraju.",
        "Nie jest łatwo wyjaśnić, dlaczego niektórzy ludzie są bardziej zmotywowani niż inni. Badania pokazują jednak, że dobre nawyki i odpowiednia ilość snu mają duże znaczenie.",
        "W zeszłym roku firma zwiększyła przychody o dwanaście procent, głównie dzięki nowym klientom za granicą.",
        "Pacjent został przyjęty do szpitala z gorączką i bólem głowy. Lekarze przepisali mu antybiotyki i zalecili odpoczynek.",
        "Ten rozdział opisuje, jak przebiega fotosynteza i dlaczego rośliny są tak ważne dla życia na Ziemi.",
        "W środę będzie przeważnie pochmurno, po południu miejscami przelotne opady, a temperatura wyniesie około piętnastu stopni.",
    ],
    "cs": [
        "Vláda dnes schválila nový zákon o vzdělávání. Podle ministra začne reforma příští rok a bude se týkat všech základních škol v zemi.",
        "Není snadné vysvětlit, proč jsou někteří lidé motivovanější než jiní. Výzkumy však ukazují, že dobré návyky a dostatek spánku mají velký vliv.",
        "Společnost loni zvýšila tržby o dvanáct procent, hlavně díky novým zákazníkům v zahraničí a lepším cenám surovin.",
        "Pacient byl přijat do nemocnice s horečkou a bolestí hlavy. Lékaři mu předepsali antibiotika a doporučili klid na lůžku.",
        "Tato kapitola popisuje, jak funguje fotosyntéza a proč jsou rostliny důležité pro život na Zemi.",
        "Ve středu bude převážně oblačno, odpoledne místy přeháňky a teploty kolem patnácti stupňů.",
    ],
    "sk": [
        "Vláda dnes schválila nový zákon o vzdelávaní. Podľa ministra sa reforma začne budúci rok a bude sa týkať všetkých základných škôl v krajine.",
        "Nie je ľahké vysvetliť, prečo sú niektorí ľudia motivovanejší ako iní. Výskumy však ukazujú, že dobré návyky a dostatok spánku majú veľký vplyv.",
        "Spoločnosť minulý rok zvýšila tržby o dvanásť percent, najmä vďaka novým zákazníkom v zahraničí a lepším cenám surovín.",
        "Pacient bol prijatý do nemocnice s horúčkou a bolesťou hlavy. Lekári mu predpísali antibiotiká a odporučili pokoj na lôžku.",
        "Táto kapitola opisuje, ako funguje fotosyntéza a prečo sú rastliny dôležité pre život na Zemi.",
        "V stredu bude prevažne oblačno, popoludní miestami prehánky a teploty okolo pätnástich stupňov.",
    ],
    "sl": [
        "Vlada je danes sprejela nov zakon o izobraževanju. Po besedah ministra se bo reforma začela prihodnje leto in bo zajela vse osnovne šole v državi.",
        "Ni lahko pojasniti, zakaj so nekateri ljudje bolj motivirani kot drugi. Raziskave pa kažejo, da imajo dobre navade in dovolj spanja velik vpliv.",
        "Lani je podjetje povečalo prihodke za dvanajst odstotkov, predvsem zaradi novih strank v tujini.",
        "Bolnik je bil sprejet v bolnišnico z vročino in glavobolom. Zdravniki so mu predpisali antibiotike in priporočili počitek.",
        "To poglavje opisuje, kako poteka fotosinteza in zakaj so rastline tako pomembne za življenje na Zemlji.",
        "V sredo bo pretežno oblačno, popoldne bodo ponekod plohe, temperature pa bodo okoli petnajst stopinj.",
    ],
    "hr": [
        "Vlada Republike Hrvatske danas je usvojila novi zakon o obrazovanju. Prema riječima ministra, reforma će započeti sljedeće godine i obuhvatit će sve osnovne škole.",
        "Nije lako objasniti zašto su neki ljudi motiviraniji od drugih. Istraživanja ipak pokazuju da dobre navike i dovoljno sna imaju velik utjecaj.",
        "Prošle godine tvrtka je povećala prihode za dvanaest posto, uglavnom zahvaljujući novim kupcima u inozemstvu.",
        "Pacijent je primljen u bolnicu s visokom temperaturom i glavoboljom. Liječnici su mu propisali antibiotike i preporučili odmor.",
        "Ovo poglavlje opisuje kako se odvija fotosinteza i zašto su biljke toliko važne za život na Zemlji.",
        "U srijedu će biti pretežno oblačno, poslijepodne mjestimice pljuskovi, a temperatura oko petnaest stupnjeva.",
    ],
    "sr-latn": [
        "Vlada Srbije je danas usvojila novi zakon o obrazovanju. Prema rečima ministra, reforma će početi sledeće godine i obuhvatiće sve osnovne škole.",
        "Nije lako objasniti zašto su neki ljudi motivisaniji od drugih. Istraživanja ipak pokazuju da dobre navike i dovoljno sna imaju veliki uticaj.",
        "Prošle godine kompanija je povećala prihode za dvanaest procenata, uglavnom zahvaljujući novim kupcima u inostranstvu.",
        "Pacijent je primljen u bolnicu sa visokom temperaturom i glavoboljom. Lekari su mu prepisali antibiotike i preporučili odmor.",
        "Ovo poglavlje objašnjava kako funkcioniše fotosinteza i zašto su biljke važne za ceo svet.",
        "U sredu će biti pretežno oblačno, posle podne mestimično pljuskovi, a temperatura oko petnaest stepeni.",
    ],
    "bg": [
        "Правителството днес прие нов закон за образованието. Според министъра реформата ще започне догодина и ще обхване всички основни училища в страната.",
        "Не е лесно да се обясни защо някои хора са по-мотивирани от други. Изследванията обаче показват, че добрите навици и достатъчният сън имат голямо значение.",
        "Миналата година компанията увеличи приходите си с дванадесет процента, главно благодарение на нови клиенти в чужбина.",
        "Пациентът беше приет в болница с висока температура и главоболие. Лекарите му предписаха антибиотици и препоръчаха почивка.",
        "Тази глава описва как протича фотосинтезата и защо растенията са толкова важни за живота на Земята.",
        "В сряда ще бъде предимно облачно, следобед на места ще има превалявания, а температурите ще бъдат около петнадесет градуса.",
    ],
    "mk": [
        "Владата денеска усвои нов закон за образование. Според министерот, реформата ќе започне следната година и ќе ги опфати сите основни училишта.",
        "Не е лесно да се објасни зошто некои луѓе се помотивирани од други. Истражувањата сепак покажуваат дека добрите навики и доволно сон имаат големо влијание.",
        "Минатата година компанијата ги зголеми приходите за дванаесет проценти, главно благодарение на новите клиенти во странство.",
        "Пациентот беше примен во болница со висока температура и главоболка. Лекарите му препишаа антибиотици и му препорачаа одмор.",
        "Ова поглавје опишува како се одвива фотосинтезата и зошто растенијата се толку важни за животот на Земјата.",
        "Во среда ќе биде претежно облачно, попладне на места пороен дожд, а температурата ќе биде околу петнаесет степени.",
    ],
    "sr": [
        "Влада Србије је данас усвојила нови закон о образовању. Према речима министра, реформа ће почети следеће године и обухватиће све основне школе.",
        "Није лако објаснити зашто су неки људи мотивисанији од других. Истраживања ипак показују да добре навике и довољно сна имају велики утицај.",
        "Прошле године компанија је повећала приходе за дванаест процената, углавном захваљујући новим купцима у иностранству.",
        "Пацијент је примљен у болницу са високом температуром и главобољом. Лекари су му преписали антибиотике и препоручили одмор.",
        "Ово поглавље објашњава како функционише фотосинтеза и зашто су биљке важне за цео свет.",
        "У среду ће бити претежно облачно, после подне местимично пљускови, а температура око петнаест степени.",
    ],
    "ru": [
        "Правительство сегодня приняло новый закон об образовании. По словам министра, реформа начнётся в следующем году и охватит все начальные школы страны.",
        "Нелегко объяснить, почему одни люди мотивированы больше других. Однако исследования показывают, что хорошие привычки и достаточный сон имеют большое значение.",
        "В прошлом году компания увеличила выручку на двенадцать процентов, главным образом благодаря новым клиентам за рубежом.",
        "Пациент был госпитализирован с высокой температурой и головной болью. Врачи назначили ему антибиотики и рекомендовали покой.",
        "В этой главе описывается, как происходит фотосинтез и почему растения так важны для жизни на Земле.",
        "В среду будет преимущественно облачно, днём местами кратковременные дожди, температура около пятнадцати градусов.",
    ],
    "uk": [
        "Уряд сьогодні ухвалив новий закон про освіту. За словами міністра, реформа розпочнеться наступного року і охопить усі початкові школи країни.",
        "Нелегко пояснити, чому одні люди мотивовані більше за інших. Проте дослідження показують, що добрі звички й достатній сон мають велике значення.",
        "Минулого року компанія збільшила виручку на дванадцять відсотків, головним чином завдяки новим клієнтам за кордоном.",
        "Пацієнта госпіталізували з високою температурою та головним болем. Лікарі призначили йому антибіотики й порадили відпочинок.",
        "У цьому розділі описано, як відбувається фотосинтез і чому рослини такі важливі для життя на Землі.",
        "У середу буде переважно хмарно, вдень місцями короткочасні дощі, температура близько п'ятнадцяти градусів.",
    ],
}
CZECH_TEXTS = SLAVIC["cs"]
SLOVAK_TEXTS = SLAVIC["sk"]
# Siblings langdetect is most likely to confuse each language with.
SLAVIC_SIBLINGS = {
    "cs": ["sk", "pl"], "sk": ["cs", "pl"], "pl": ["cs", "sk"], "sl": ["hr"], "hr": ["sl"],
    "sr-latn": ["hr", "sl"], "bg": ["mk", "ru"], "mk": ["bg", "ru"], "sr": ["mk", "bg", "ru"],
    "ru": ["mk", "uk", "bg"], "uk": ["ru", "mk"],
}


def letter_spaced(text: str) -> str:
    """How design-tool PDFs extract: 'T H E  P L A N' (double space between words)."""
    return "  ".join(" ".join(word) for word in text.split())


class _MultilingualOn(unittest.TestCase):
    def setUp(self):
        self._saved = settings.MULTILINGUAL_ENABLED
        settings.MULTILINGUAL_ENABLED = True

    def tearDown(self):
        settings.MULTILINGUAL_ENABLED = self._saved


# --------------------------------------------------------------------------- #
# Every supported language
# --------------------------------------------------------------------------- #
class TestSupportedLanguages(_MultilingualOn):
    def test_every_profile_has_a_sample(self):
        self.assertEqual(set(LANGUAGE_PROFILES), set(SAMPLES))

    def test_each_language_detected(self):
        for code, text in SAMPLES.items():
            with self.subTest(code=code):
                self.assertEqual(detect_language(text * 3), code)

    def test_each_language_detected_when_letter_spaced(self):
        for code, text in SAMPLES.items():
            with self.subTest(code=code):
                self.assertEqual(detect_language(letter_spaced(text * 3)), code)

    def test_each_language_detected_in_long_document(self):
        """Long docs use three windows; a uniform document must still win."""
        for code, text in SAMPLES.items():
            with self.subTest(code=code):
                self.assertEqual(detect_language(text * 60), code)

    def test_danish_and_norwegian_stay_apart(self):
        for code in ("da", "no"):
            with self.subTest(code=code):
                self.assertEqual(detect_language(SAMPLES[code] * 60), code)
        nynorsk = "Regjeringa la i dag fram ei ny lov om utdanning. Ifølgje statsråden skal reforma starte neste år og omfatte alle barneskular i landet. Lærarane er positive til planen, men seier at det trengst meir pengar."
        self.assertEqual(detect_language(nynorsk * 3), "no")

    def test_unsupported_lookalikes_stay_english(self):
        self.assertEqual(detect_language(ROMANIAN * 3), "en")
        self.assertEqual(detect_language(HUNGARIAN * 3), "en")

    def test_slavic_neighbours_stay_apart(self):
        for code, texts in SLAVIC.items():
            for text in texts:
                for label, doc in (("1x", text), ("3x", text * 3), ("long", text * 60),
                                   ("letter-spaced", letter_spaced(text * 3))):
                    with self.subTest(code=code, text=text[:30], form=label):
                        self.assertEqual(detect_language(doc), code)

    def test_slavic_tie_breakers_overrule_a_wrong_langdetect_call(self):
        """If langdetect ever names a close sibling, letters/function words decide."""
        import langdetect

        real = langdetect.detect
        try:
            for code, siblings in SLAVIC_SIBLINGS.items():
                for wrong in siblings:
                    langdetect.detect = lambda text, wrong=wrong: wrong
                    for text in SLAVIC[code]:
                        with self.subTest(code=code, forced=wrong, text=text[:30]):
                            self.assertEqual(detect_language(text * 3), code)
        finally:
            langdetect.detect = real

    def test_stray_slovak_letter_does_not_flip_czech(self):
        # A German name with "ä" inside Czech text must not make it Slovak.
        czech = CZECH_TEXTS[2] + " Ředitelem je pan Bär z Mnichova, který řídí pobočku v Brně."
        self.assertEqual(detect_language(czech * 3), "cs")


# --------------------------------------------------------------------------- #
# English inputs that must never become another language
# --------------------------------------------------------------------------- #
class TestEnglishStaysEnglish(_MultilingualOn):
    CASES = {
        "plain": ENGLISH * 3,
        # The real-world bug: a Canva-style PDF read as Welsh.
        "letter-spaced": letter_spaced(WORKPLACE * 6),
        "letter-spaced title then prose": letter_spaced("THE FILIPINO IN THE ORGANIZATION") + "\n\n" + WORKPLACE * 6,
        "all caps": (ENGLISH * 3).upper(),
        "numbers and tables": "Q1 2024 Revenue 1,234 5,678 9.1% Q2 2024 Revenue 2,345 6,789 8.4% " * 12 + ENGLISH,
        "bibliography": "Smith, J., Kowalski, A., & Nguyen, T. (2021). Journal of Applied Psychology, 106(4), 512-530. Garcia, M. et al. (2019). Proc. IEEE CVPR, pp. 1123-1131. " * 8,
        "code heavy": "def main(args):\n    for i in range(10):\n        print(i, args.verbose)\n    return 0\n" * 10 + ENGLISH,
        "local terms": "The Filipino worker values pakikisama, bayanihan and utang na loob in the workplace. Hiya and amor propio shape how employees respond to criticism. " * 8,
        "cover page": "HBO PA 15 Lesson 1 and 2. Prepared by Prof. Maria Santos, BSBA Department. " * 3 + ENGLISH * 3,
        "ocr noise": "Th e qu ick br own fo x jum ps ov er th e la zy d og. Im port ant no tes ab out the le sson are bel ow. " * 10,
    }

    def test_cases(self):
        for name, text in self.CASES.items():
            with self.subTest(case=name):
                self.assertEqual(detect_language(text), "en")
                self.assertEqual(detect_language_name(text), "English (en)")


# --------------------------------------------------------------------------- #
# Mixed-language documents (three-window majority vote)
# --------------------------------------------------------------------------- #
class TestMixedDocuments(_MultilingualOn):
    def test_foreign_doc_with_some_english_keeps_its_language(self):
        self.assertEqual(detect_language(SAMPLES["de"] * 3 + " " + ENGLISH), "de")
        self.assertEqual(detect_language(SAMPLES["ar"] * 4 + " (PDF, API, AI, Machine Learning)"), "ar")

    def test_english_report_with_foreign_abstract_first_stays_english(self):
        """Only the opening is French: one window of three, so English wins."""
        doc = SAMPLES["fr"] * 22 + "\n\n" + ENGLISH * 80
        self.assertEqual(detect_language(doc), "en")

    def test_foreign_paper_with_english_references_keeps_its_language(self):
        doc = SAMPLES["fr"] * 90 + "\n\nReferences\n" + ENGLISH * 25
        self.assertEqual(detect_language(doc), "fr")

    def test_garbled_section_does_not_decide(self):
        doc = ENGLISH * 30 + "£$%^ ÃƒÂ© ¤¤ ¦¦ " * 400 + ENGLISH * 30
        self.assertEqual(detect_language(doc), "en")

    def test_no_majority_falls_back_to_english(self):
        doc = SAMPLES["de"] * 30 + SAMPLES["fr"] * 33 + SAMPLES["es"] * 37
        self.assertEqual(detect_language(doc), "en")
        self.assertTrue(detect_language_name(doc).startswith("Mixed: "))


# --------------------------------------------------------------------------- #
# English safety check (independent of langdetect)
# --------------------------------------------------------------------------- #
ENGLISH_PROSE = {
    "plain": ENGLISH * 3,
    "workplace": WORKPLACE * 6,
    "letter-spaced": letter_spaced(WORKPLACE * 6),
    "all caps": (ENGLISH * 3).upper(),
    "local terms": TestEnglishStaysEnglish.CASES["local terms"],
}


class TestEnglishSafetyCheck(_MultilingualOn):
    def test_english_prose_clears_the_bar(self):
        for name, text in ENGLISH_PROSE.items():
            with self.subTest(case=name):
                share = languages._english_share(languages._detection_samples(text)[0])
                self.assertGreaterEqual(share, languages._ENGLISH_SHARE_MIN)

    def test_foreign_languages_stay_well_below_the_bar(self):
        mixed = {
            "de + 25% English": SAMPLES["de"] * 3 + " " + ENGLISH,
            "fr + 25% English": SAMPLES["fr"] * 4 + " " + ENGLISH,
            "ru + English quote": SAMPLES["ru"] * 4 + ' "' + ENGLISH[:120] + '"',
            "zh + English terms": SAMPLES["zh"] * 4 + " machine learning, PDF, API",
        }
        for name, text in {**{k: v * 3 for k, v in SAMPLES.items()}, **mixed}.items():
            with self.subTest(case=name):
                share = languages._english_share(languages._detection_samples(text)[0])
                self.assertLess(share, languages._ENGLISH_SHARE_MIN / 1.5)

    def test_english_stays_english_even_when_langdetect_is_wrong(self):
        """The disaster case: langdetect calls an English document Welsh."""
        import langdetect

        real = langdetect.detect
        langdetect.detect = lambda text: "cy"
        try:
            for name, text in ENGLISH_PROSE.items():
                with self.subTest(case=name):
                    self.assertEqual(detect_language(text), "en")
                    self.assertEqual(detect_language(text * 40), "en")  # 3-window path
        finally:
            langdetect.detect = real

    def test_foreign_with_english_quotes_keeps_its_language(self):
        self.assertEqual(detect_language(SAMPLES["ru"] * 4 + ' "' + ENGLISH[:120] + '"'), "ru")
        self.assertEqual(detect_language(SAMPLES["zh"] * 4 + " machine learning, PDF, API"), "zh")


# --------------------------------------------------------------------------- #
# Detection row in the admin notification email
# --------------------------------------------------------------------------- #
class TestDetectionConfidence(_MultilingualOn):
    def test_labels(self):
        conf = languages.detection_confidence
        self.assertEqual(conf(ENGLISH * 3), "1 sample (short document)")
        self.assertEqual(conf(SAMPLES["fr"] * 90), "3/3 samples agree")
        self.assertEqual(
            conf(SAMPLES["fr"] * 90 + "\n\nReferences\n" + ENGLISH * 25),
            "⚠︎ 2/3 samples agree (fr, fr, en)",
        )
        self.assertEqual(
            conf(SAMPLES["de"] * 30 + SAMPLES["fr"] * 33 + SAMPLES["es"] * 37),
            "⚠︎ no majority (de, fr, es) — English used",
        )
        self.assertEqual(conf("Hi"), "Unknown (too little text)")

    def test_flags_letter_spaced_text(self):
        doc = letter_spaced(WORKPLACE * 40)
        self.assertEqual(detect_language(doc), "en")
        self.assertEqual(languages.detection_confidence(doc), "3/3 samples agree · ⚠︎ letter-spaced text fixed")


# --------------------------------------------------------------------------- #
# Guards and helpers
# --------------------------------------------------------------------------- #
class TestGuards(unittest.TestCase):
    def test_flag_off_is_always_english(self):
        saved = settings.MULTILINGUAL_ENABLED
        settings.MULTILINGUAL_ENABLED = False
        try:
            self.assertEqual(detect_language(SAMPLES["fr"] * 3), "en")
        finally:
            settings.MULTILINGUAL_ENABLED = saved

    def test_short_text_is_english(self):
        saved = settings.MULTILINGUAL_ENABLED
        settings.MULTILINGUAL_ENABLED = True
        try:
            self.assertEqual(detect_language("Bonjour"), "en")
            self.assertEqual(detect_language_name("Bonjour"), "Unknown")
        finally:
            settings.MULTILINGUAL_ENABLED = saved

    def test_unspacing_leaves_normal_text_untouched(self):
        normal = [t for k, t in TestEnglishStaysEnglish.CASES.items() if "letter-spaced" not in k]
        for text in list(SAMPLES.values()) + normal:
            with self.subTest(text=text[:40]):
                self.assertEqual(languages._unspace_letters(text), text)

    def test_unspacing_restores_words(self):
        self.assertEqual(
            languages._unspace_letters(letter_spaced("THE FILIPINO IN THE ORGANIZATION")),
            "THE FILIPINO IN THE ORGANIZATION",
        )

    def test_names_for_refined_languages(self):
        self.assertEqual(detect_language_name(SAMPLES["sr"] * 3), "Serbian (sr)")
        self.assertEqual(detect_language_name(SAMPLES["sr-latn"] * 3), "Serbian (Latin) (sr-latn)")
        self.assertEqual(detect_language_name(SAMPLES["ms"] * 3), "Malay (ms)")
        self.assertEqual(detect_language_name(SAMPLES["id"] * 3), "Indonesian (id)")


if __name__ == "__main__":
    unittest.main()
