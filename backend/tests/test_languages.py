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
    "zh-tw": "政府今天通過了一項新的教育法。部長表示，改革將於明年開始，並覆蓋全國所有小學。教師們歡迎這項計劃，但表示需要更多資金。",
    "ja": "政府は本日、新しい教育法を可決した。大臣によると、改革は来年から始まり、全国のすべての小学校が対象となる。",
    "fi": "Hallitus hyväksyi tänään uuden koulutuslain. Ministerin mukaan uudistus alkaa ensi vuonna ja koskee kaikkia maan peruskouluja.",
    "et": "Valitsus kiitis täna heaks uue haridusseaduse. Ministri sõnul algab reform järgmisel aastal ja hõlmab kõiki riigi põhikoole.",
    "az": "Hökumət bu gün təhsil haqqında yeni qanun qəbul etdi. Nazirin sözlərinə görə, islahat gələn il başlayacaq və ölkənin bütün ibtidai məktəblərini əhatə edəcək.",
    "ko": "정부는 오늘 새로운 교육법을 통과시켰다. 장관에 따르면 개혁은 내년에 시작되며 전국의 모든 초등학교에 적용될 예정이다.",
    "hu": "A kormány ma új oktatási törvényt fogadott el. A miniszter szerint a reform jövőre kezdődik, és az ország összes általános iskolájára kiterjed.",
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

# CJK and Uralic/Turkic lanes. Six parallel texts each; LANE_EXPECTED is the
# language the podcast must be in (unsupported look-alikes -> English). Chinese
# Traditional must be Chinese: langdetect alone calls it Korean.
LANES = {
    "zh": [
        "政府今天通过了一项新的教育法。部长表示，改革将于明年开始，并覆盖全国所有小学。",
        "要解释为什么有些人比其他人更有动力并不容易。但研究表明，良好的习惯和充足的睡眠有很大影响。",
        "该公司去年的收入增长了百分之十二，主要得益于海外的新客户。",
        "病人因高烧和头痛住院。医生给他开了抗生素，并建议他休息。",
        "本章介绍光合作用是如何进行的，以及植物为什么对地球上的生命如此重要。",
        "周三以多云为主，下午局部有阵雨，气温在十五度左右。",
    ],
    "zh-trad": [
        "政府今天通過了一項新的教育法。部長表示，改革將於明年開始，並覆蓋全國所有小學。",
        "要解釋為什麼有些人比其他人更有動力並不容易。但研究表明，良好的習慣和充足的睡眠有很大影響。",
        "該公司去年的收入增長了百分之十二，主要得益於海外的新客戶。",
        "病人因高燒和頭痛住院。醫生給他開了抗生素，並建議他休息。",
        "本章介紹光合作用是如何進行的，以及植物為什麼對地球上的生命如此重要。",
        "週三以多雲為主，下午局部有陣雨，氣溫在十五度左右。",
    ],
    "ja": [
        "政府は本日、新しい教育法を可決した。大臣によると、改革は来年から始まり、全国のすべての小学校が対象となる。",
        "なぜ一部の人が他の人よりも意欲的なのかを説明するのは簡単ではない。しかし研究によれば、良い習慣と十分な睡眠が大きな影響を与える。",
        "同社は昨年、海外の新規顧客のおかげで売上を12パーセント伸ばした。",
        "患者は高熱と頭痛で入院した。医師は抗生物質を処方し、安静を勧めた。",
        "この章では、光合成がどのように行われるのか、そして植物が地球上の生命にとってなぜ重要なのかを説明する。",
        "水曜日はおおむね曇りで、午後は所により雨が降り、気温は15度前後となる見込みだ。",
    ],
    "ko": [
        "정부는 오늘 새로운 교육법을 통과시켰다. 장관에 따르면 개혁은 내년에 시작되며 전국의 모든 초등학교에 적용될 예정이다.",
        "왜 어떤 사람들이 다른 사람들보다 더 동기 부여가 되는지 설명하기는 쉽지 않다. 그러나 연구에 따르면 좋은 습관과 충분한 수면이 큰 영향을 미친다.",
        "회사는 작년에 해외 신규 고객 덕분에 매출을 12퍼센트 늘렸다.",
        "환자는 고열과 두통으로 병원에 입원했다. 의사들은 항생제를 처방하고 휴식을 권했다.",
        "이 장에서는 광합성이 어떻게 일어나는지, 그리고 식물이 지구상의 생명에 왜 중요한지를 설명한다.",
        "수요일에는 대체로 흐리고 오후에는 곳곳에 소나기가 내리며 기온은 15도 안팎이 되겠다.",
    ],
    "hu": [
        "A kormány ma új oktatási törvényt fogadott el. A miniszter szerint a reform jövőre kezdődik, és az ország összes általános iskolájára kiterjed.",
        "Nem könnyű megmagyarázni, miért motiváltabbak egyes emberek másoknál. A kutatások azonban azt mutatják, hogy a jó szokások és az elegendő alvás nagy hatással vannak.",
        "A vállalat tavaly tizenkét százalékkal növelte bevételét, főként a külföldi új ügyfeleknek köszönhetően.",
        "A beteget magas lázzal és fejfájással vették fel a kórházba. Az orvosok antibiotikumot írtak fel neki, és pihenést javasoltak.",
        "Ez a fejezet bemutatja, hogyan zajlik a fotoszintézis, és miért olyan fontosak a növények a földi élet szempontjából.",
        "Szerdán többnyire felhős lesz az ég, délután helyenként záporok várhatók, a hőmérséklet tizenöt fok körül alakul.",
    ],
    "fi": [
        "Hallitus hyväksyi tänään uuden koulutuslain. Ministerin mukaan uudistus alkaa ensi vuonna ja koskee kaikkia maan peruskouluja.",
        "Ei ole helppo selittää, miksi jotkut ihmiset ovat motivoituneempia kuin toiset. Tutkimukset kuitenkin osoittavat, että hyvillä tavoilla ja riittävällä unella on suuri vaikutus.",
        "Yhtiö kasvatti viime vuonna liikevaihtoaan kaksitoista prosenttia, pääasiassa uusien ulkomaisten asiakkaiden ansiosta.",
        "Potilas otettiin sairaalaan korkean kuumeen ja päänsäryn vuoksi. Lääkärit määräsivät hänelle antibiootteja ja suosittelivat lepoa.",
        "Tässä luvussa kuvataan, miten fotosynteesi tapahtuu ja miksi kasvit ovat niin tärkeitä elämälle maapallolla.",
        "Keskiviikkona on enimmäkseen pilvistä, iltapäivällä paikoin sadekuuroja ja lämpötila noin viisitoista astetta.",
    ],
    "et": [
        "Valitsus kiitis täna heaks uue haridusseaduse. Ministri sõnul algab reform järgmisel aastal ja hõlmab kõiki riigi põhikoole.",
        "Pole lihtne seletada, miks mõned inimesed on teistest motiveeritumad. Uuringud näitavad siiski, et headel harjumustel ja piisaval unel on suur mõju.",
        "Ettevõte suurendas eelmisel aastal käivet kaksteist protsenti, peamiselt tänu uutele välismaistele klientidele.",
        "Patsient võeti haiglasse kõrge palaviku ja peavaluga. Arstid määrasid talle antibiootikume ja soovitasid puhkust.",
        "Selles peatükis kirjeldatakse, kuidas fotosüntees toimub ja miks taimed on elu jaoks Maal nii olulised.",
        "Kolmapäeval on peamiselt pilves, pärastlõunal kohati hoovihmad ja temperatuur on umbes viisteist kraadi.",
    ],
    "az": [
        "Hökumət bu gün təhsil haqqında yeni qanun qəbul etdi. Nazirin sözlərinə görə, islahat gələn il başlayacaq və ölkənin bütün ibtidai məktəblərini əhatə edəcək.",
        "Bəzi insanların niyə digərlərindən daha motivasiyalı olduğunu izah etmək asan deyil. Lakin araşdırmalar göstərir ki, yaxşı vərdişlər və kifayət qədər yuxu böyük təsir göstərir.",
        "Şirkət keçən il əsasən xaricdəki yeni müştərilər sayəsində gəlirini on iki faiz artırdı.",
        "Xəstə yüksək hərarət və baş ağrısı ilə xəstəxanaya yerləşdirildi. Həkimlər ona antibiotik yazdı və istirahət tövsiyə etdi.",
        "Bu fəsil fotosintezin necə baş verdiyini və bitkilərin Yer üzündə həyat üçün niyə bu qədər vacib olduğunu izah edir.",
        "Çərşənbə günü hava əsasən buludlu olacaq, günortadan sonra bəzi yerlərdə leysan yağışları gözlənilir və temperatur on beş dərəcə ətrafında olacaq.",
    ],
    "tr": [
        "Hükümet bugün eğitimle ilgili yeni bir yasa kabul etti. Bakana göre reform gelecek yıl başlayacak ve ülkedeki tüm ilkokulları kapsayacak.",
        "Bazı insanların neden diğerlerinden daha motive olduğunu açıklamak kolay değil. Ancak araştırmalar, iyi alışkanlıkların ve yeterli uykunun büyük etkisi olduğunu gösteriyor.",
        "Şirket geçen yıl, özellikle yurt dışındaki yeni müşteriler sayesinde gelirini yüzde on iki artırdı.",
        "Hasta yüksek ateş ve baş ağrısıyla hastaneye kaldırıldı. Doktorlar ona antibiyotik yazdı ve dinlenmesini önerdi.",
        "Bu bölüm, fotosentezin nasıl gerçekleştiğini ve bitkilerin Dünya'daki yaşam için neden bu kadar önemli olduğunu açıklıyor.",
        "Çarşamba günü hava çoğunlukla bulutlu olacak, öğleden sonra yer yer sağanak yağış bekleniyor ve sıcaklık on beş derece civarında olacak.",
    ],
}
LANE_EXPECTED = {"zh": "zh", "zh-trad": "zh-tw", "ja": "ja", "ko": "ko", "hu": "hu", "fi": "fi", "et": "et", "tr": "tr", "az": "az"}
LANE_SIBLINGS = {
    "zh": ["ja", "ko"], "zh-trad": ["ja", "ko"], "ja": ["zh-cn", "ko"], "ko": ["zh-cn", "ja"],
    "hu": ["fi", "et", "tr", "sk"], "fi": ["hu", "et"], "et": ["hu", "fi"], "tr": ["hu", "az"], "az": ["tr", "hu"],
}
# Unsupported languages next to supported ones: every one must give English.
UNSUPPORTED = {
    "mr": ["सरकारने आज शिक्षणाबाबत नवीन कायदा मंजूर केला. मंत्र्यांच्या म्हणण्यानुसार ही सुधारणा पुढील वर्षी सुरू होईल आणि देशातील सर्व प्राथमिक शाळांना लागू होईल.",
           "बुधवारी आकाश मुख्यतः ढगाळ राहील, दुपारी काही ठिकाणी पावसाच्या सरी पडतील आणि तापमान सुमारे पंधरा अंश राहील.",
           "रुग्णाला ताप आणि डोकेदुखीमुळे रुग्णालयात दाखल करण्यात आले. डॉक्टरांनी त्याला प्रतिजैविके दिली आणि विश्रांती घेण्याचा सल्ला दिला."],
    "ne": ["सरकारले आज शिक्षासम्बन्धी नयाँ कानुन पारित गर्‍यो। मन्त्रीका अनुसार सुधार अर्को वर्ष सुरु हुनेछ र देशका सबै प्राथमिक विद्यालयमा लागू हुनेछ।",
           "बुधबार आकाश प्रायः बादल लागेको रहनेछ, दिउँसो केही ठाउँमा वर्षा हुनेछ र तापक्रम करिब पन्ध्र डिग्री रहनेछ।",
           "बिरामीलाई ज्वरो र टाउको दुखाइका कारण अस्पताल भर्ना गरियो। डाक्टरहरूले उनलाई एन्टिबायोटिक दिए र आराम गर्न सल्लाह दिए।"],
    "ca": ["El govern ha aprovat avui una nova llei d'educació. Segons el ministre, la reforma començarà l'any vinent i afectarà totes les escoles primàries del país.",
           "Dimecres estarà majoritàriament ennuvolat, a la tarda hi haurà ruixats en alguns punts i les temperatures seran d'uns quinze graus.",
           "El pacient va ingressar a l'hospital amb febre alta i mal de cap. Els metges li van receptar antibiòtics i li van recomanar repòs."],
    "sv": ["Regeringen har i dag antagit en ny lag om utbildning. Enligt ministern börjar reformen nästa år och omfattar alla grundskolor i landet.",
           "På onsdag blir det mestadels mulet, på eftermiddagen lokala skurar och temperaturer runt femton grader.",
           "Patienten lades in på sjukhuset med hög feber och huvudvärk. Läkarna skrev ut antibiotika och rekommenderade vila."],
    "af": ["Die regering het vandag 'n nuwe wet oor onderwys aanvaar. Volgens die minister sal die hervorming volgende jaar begin en alle laerskole in die land insluit.",
           "Woensdag sal dit meestal bewolk wees, met plek-plek buie in die middag en temperature van ongeveer vyftien grade.",
           "Die pasiënt is met hoë koors en hoofpyn in die hospitaal opgeneem. Die dokters het antibiotika voorgeskryf en rus aanbeveel."],
    "lv": ["Valdība šodien pieņēma jaunu izglītības likumu. Pēc ministra teiktā, reforma sāksies nākamgad un aptvers visas valsts pamatskolas.",
           "Trešdien būs pārsvarā mākoņains, pēcpusdienā vietām lietusgāzes, un temperatūra būs ap piecpadsmit grādiem.",
           "Pacients tika ievietots slimnīcā ar augstu drudzi un galvassāpēm. Ārsti viņam izrakstīja antibiotikas un ieteica atpūtu."],
    "ro": ["Guvernul a adoptat astăzi o nouă lege a educației. Potrivit ministrului, reforma va începe anul viitor și va cuprinde toate școlile primare din țară.",
           "Miercuri va fi în mare parte înnorat, după-amiază vor fi averse pe alocuri, iar temperaturile vor fi în jur de cincisprezece grade.",
           "Pacientul a fost internat în spital cu febră mare și dureri de cap. Medicii i-au prescris antibiotice și i-au recomandat odihnă."],
    "bn": ["সরকার আজ শিক্ষা বিষয়ে একটি নতুন আইন পাস করেছে। মন্ত্রীর মতে, সংস্কার আগামী বছর শুরু হবে এবং দেশের সব প্রাথমিক বিদ্যালয়ে প্রযোজ্য হবে।"],
    "gu": ["સરકારે આજે શિક્ષણ અંગે નવો કાયદો પસાર કર્યો. મંત્રીના જણાવ્યા અનુસાર સુધારો આવતા વર્ષે શરૂ થશે અને દેશની તમામ પ્રાથમિક શાળાઓને લાગુ પડશે."],
    "pa": ["ਸਰਕਾਰ ਨੇ ਅੱਜ ਸਿੱਖਿਆ ਬਾਰੇ ਇੱਕ ਨਵਾਂ ਕਾਨੂੰਨ ਪਾਸ ਕੀਤਾ। ਮੰਤਰੀ ਦੇ ਅਨੁਸਾਰ ਸੁਧਾਰ ਅਗਲੇ ਸਾਲ ਸ਼ੁਰੂ ਹੋਵੇਗਾ ਅਤੇ ਦੇਸ਼ ਦੇ ਸਾਰੇ ਪ੍ਰਾਇਮਰੀ ਸਕੂਲਾਂ 'ਤੇ ਲਾਗੂ ਹੋਵੇਗਾ।"],
    "he": ["הממשלה אישרה היום חוק חינוך חדש. לדברי השר, הרפורמה תתחיל בשנה הבאה ותחול על כל בתי הספר היסודיים בארץ."],
    "th": ["รัฐบาลได้อนุมัติกฎหมายการศึกษาฉบับใหม่ในวันนี้ รัฐมนตรีกล่าวว่าการปฏิรูปจะเริ่มในปีหน้าและครอบคลุมโรงเรียนประถมทุกแห่งในประเทศ"],
    "sq": ["Qeveria miratoi sot një ligj të ri për arsimin. Sipas ministrit, reforma do të fillojë vitin e ardhshëm dhe do të përfshijë të gjitha shkollat fillore në vend."],
    "sw": ["Serikali leo imepitisha sheria mpya ya elimu. Kwa mujibu wa waziri, mageuzi yataanza mwaka ujao na yatahusu shule zote za msingi nchini."],
    "tl": ["Inaprubahan ngayon ng pamahalaan ang isang bagong batas sa edukasyon. Ayon sa ministro, magsisimula ang reporma sa susunod na taon at sasaklawin nito ang lahat ng paaralang elementarya sa bansa."],
    "so": ["Dowladdu maanta waxay meel marisay sharci cusub oo ku saabsan waxbarashada. Sida uu sheegay wasiirku, dib-u-habeyntu waxay bilaabaneysaa sanadka soo socda."],
    "ta": ["அரசு இன்று கல்வி தொடர்பான புதிய சட்டத்தை நிறைவேற்றியது. அமைச்சரின் கூற்றுப்படி, சீர்திருத்தம் அடுத்த ஆண்டு தொடங்கி நாட்டின் அனைத்து தொடக்கப் பள்ளிகளுக்கும் பொருந்தும்."],
    "te": ["ప్రభుత్వం ఈరోజు విద్యపై కొత్త చట్టాన్ని ఆమోదించింది. మంత్రి ప్రకారం, సంస్కరణ వచ్చే సంవత్సరం ప్రారంభమై దేశంలోని అన్ని ప్రాథమిక పాఠశాలలకు వర్తిస్తుంది."],
    "kn": ["ಸರ್ಕಾರ ಇಂದು ಶಿಕ್ಷಣದ ಕುರಿತು ಹೊಸ ಕಾನೂನನ್ನು ಅಂಗೀಕರಿಸಿದೆ. ಸಚಿವರ ಪ್ರಕಾರ ಸುಧಾರಣೆ ಮುಂದಿನ ವರ್ಷ ಆರಂಭವಾಗಲಿದ್ದು ದೇಶದ ಎಲ್ಲಾ ಪ್ರಾಥಮಿಕ ಶಾಲೆಗಳಿಗೆ ಅನ್ವಯಿಸಲಿದೆ."],
    "ml": ["സർക്കാർ ഇന്ന് വിദ്യാഭ്യാസം സംബന്ധിച്ച പുതിയ നിയമം പാസാക്കി. മന്ത്രിയുടെ അഭിപ്രായത്തിൽ പരിഷ്കരണം അടുത്ത വർഷം ആരംഭിക്കുകയും രാജ്യത്തെ എല്ലാ പ്രാഥമിക വിദ്യാലയങ്ങൾക്കും ബാധകമാവുകയും ചെയ്യും."],
}
# Page 198 of a real upload (a Simplified-Chinese clinical mind map) as OCR returns it.
MIND_MAP_PAGE = """临床医学综合能力（西医）思维导图
★★★ 腹部损伤（0~3题）
检查
腹腔穿刺：首选、金标准
“外科腹部损伤章节有腹穿选腹穿”
（2017、2022、2024）
①抽出不凝血→脾、肝（含胆汁）、胰（含淀粉酶）
②抽出消化液
③结肠损伤行腹腔灌洗：含大量细菌的消化液
影像学
（2012、2021、2025）
B超和CT：脾、肝、胰损伤首选B超（否则CT），肾损伤首选CT
X线
①可有膈下新月形游离气体：胃前壁、十二指肠1部、结肠、空回肠损伤
②可有腹膜后积气：胃后壁、十二指肠2/3部损伤
剖腹探查（正中切口）
（2012、2021、2024、2025）
探查顺序：肝脾→胃→十二指肠1段、空回肠、大肠→盆腔→胃后壁、胰→十二指肠剩余段
救治顺序：完整探查后→救重的→救轻的
不要分离黏连组织（以免感染扩散）
198
"""
HINDI_TEXTS = [
    "सरकार ने आज शिक्षा पर एक नया कानून पारित किया। मंत्री के अनुसार, यह सुधार अगले साल शुरू होगा और देश के सभी प्राथमिक विद्यालयों को शामिल करेगा।",
    "मरीज़ को तेज़ बुखार और सिरदर्द के कारण अस्पताल में भर्ती किया गया। डॉक्टरों ने उसे एंटीबायोटिक दवाएं दीं और आराम करने की सलाह दी।",
    "बुधवार को आसमान ज़्यादातर बादलों से घिरा रहेगा, दोपहर में कुछ जगहों पर बारिश होगी और तापमान लगभग पंद्रह डिग्री रहेगा।",
]
# Second/third texts for lanes where several siblings are supported.
EXTRA_TEXTS = {
    "ar": ["يعاني المريض من حمى شديدة وصداع، وقد وصف له الأطباء مضادات حيوية ونصحوه بالراحة.",
           "سيكون الطقس يوم الأربعاء غائما في معظمه، مع زخات متفرقة بعد الظهر ودرجات حرارة حوالي خمس عشرة درجة."],
    "fa": ["بیمار با تب بالا و سردرد در بیمارستان بستری شد. پزشکان برای او آنتی‌بیوتیک تجویز کردند و استراحت را توصیه کردند.",
           "روز چهارشنبه هوا بیشتر ابری خواهد بود، بعدازظهر در برخی نقاط رگبار می‌بارد و دما حدود پانزده درجه خواهد بود."],
    "ur": ["مریض کو تیز بخار اور سر درد کی وجہ سے ہسپتال میں داخل کیا گیا۔ ڈاکٹروں نے اسے اینٹی بائیوٹکس دیں اور آرام کا مشورہ دیا۔",
           "بدھ کو آسمان زیادہ تر ابر آلود رہے گا، دوپہر میں کچھ جگہوں پر بارش ہوگی اور درجہ حرارت تقریباً پندرہ ڈگری رہے گا۔"],
    "da": ["Patienten blev indlagt på hospitalet med høj feber og hovedpine. Lægerne udskrev antibiotika og anbefalede hvile.",
           "På onsdag bliver det mest overskyet, om eftermiddagen lokale byger og temperaturer omkring femten grader."],
    "no": ["Pasienten ble innlagt på sykehuset med høy feber og hodepine. Legene skrev ut antibiotika og anbefalte hvile.",
           "På onsdag blir det for det meste overskyet, på ettermiddagen lokale byger og temperaturer rundt femten grader."],
}
EXTRA_SIBLINGS = {"ar": ["fa", "ur"], "fa": ["ar", "ur"], "ur": ["fa", "ar"], "da": ["no", "sv"], "no": ["da", "sv"]}


# Text SHAPES that real uploads come in (OCR'd mind maps, slides, tables, ALL
# CAPS, missing diacritics, OCR noise, looping OCR output, snippets). A Chinese
# mind map was once read as Korean; every language must survive every shape.
def _shape_bullets(t, rng):
    w, out, i = t.split(), [], 0
    while i < len(w):
        n = rng.randint(2, 4); out.append("• " + " ".join(w[i:i + n])); i += n
    return "\n".join(out)


def _shape_mindmap(t, rng):
    if " " not in t.strip():  # scripts written without spaces
        s, out, i = "".join(t.split()), [], 0
        while i < len(s):
            n = rng.randint(2, 4); out.append(("→" if i % 2 else "①") + s[i:i + n]); i += n
        return "\n".join(out)
    return "\n".join(
        f"{'①②③④⑤'[i % 5]}{x}" if i % 3 == 0 else (f"→ {x}" if i % 3 == 1 else f"{x}（20{10 + i % 15}）")
        for i, x in enumerate(t.split())
    )


def _shape_no_diacritics(t, rng):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _shape_english_terms(t, rng):
    terms = ["API", "machine learning", "CT scan", "Python", "cloud", "dashboard", "KPI", "B2B", "workflow"]
    return " ".join(x + (" " + rng.choice(terms) if i % 3 == 0 else "") for i, x in enumerate(t.split()))


def _shape_table(t, rng):
    w = t.split()
    return "\n".join(f"{w[i % len(w)]} | {2019 + i % 6} | {rng.randint(10, 999)} | {rng.randint(1, 99)}.{rng.randint(0, 9)}%" for i in range(40))


def _shape_ocr_noise(t, rng):
    return " ".join((x[:len(x) // 2] + " " + x[len(x) // 2:]) if len(x) > 5 and rng.random() < 0.25 else x for x in t.split())


def _shape_loop(t, rng):  # a few short lines repeated hundreds of times
    return "\n".join([l for l in _shape_mindmap(t, rng).split("\n") if l][:5] * 300)


STRESS_SHAPES = {
    "bullets": (_shape_bullets, 4), "mindmap": (_shape_mindmap, 4), "no-diacritics": (_shape_no_diacritics, 4),
    "UPPER": (lambda t, rng: t.upper(), 4), "+English terms": (_shape_english_terms, 4), "table": (_shape_table, 1),
    "ocr-noise": (_shape_ocr_noise, 4), "loop": (_shape_loop, 1), "tiny-60": (lambda t, rng: t[:60], 1),
}
FRENCH_LINE = "Le gouvernement a adopté aujourd'hui une nouvelle loi sur l'éducation. Selon le ministre, la réforme commencera l'année prochaine. "
# Real-world script mixes, with the language each must produce.
MIXED_SCRIPT_CASES = {
    "zh + English tech terms": ("我们使用 Python 和 machine learning 模型来分析用户数据，并通过 API 提供实时结果。" * 6, "zh"),
    "zh with ・ foreign names": ("迈克尔・乔丹和勒布朗・詹姆斯都是篮球历史上最伟大的球员之一，他们的比赛影响了几代人。" * 6, "zh"),
    "Chinese tech doc, half English": ("这个系统 uses a distributed cache and a message queue 来处理高并发请求，并且 supports horizontal scaling 和自动故障转移。" * 6, "zh"),
    "ja kanji-heavy": ("政府、新教育法を可決　全国小学校対象　来年度改革開始へ　文部科学大臣発表" * 6, "ja"),
    "ko with hanja": ("大韓民國 정부는 오늘 새로운 敎育法을 통과시켰다. 장관에 따르면 改革은 내년에 시작된다." * 6, "ko"),
    "ko + English terms": ("우리는 Python과 machine learning 모델을 사용하여 사용자 데이터를 분석하고 API로 결과를 제공한다." * 6, "ko"),
    "zh quoting Korean": ("这本书介绍了韩国文化。书中引用了一句话：“안녕하세요”，意思是你好。作者认为语言是了解文化的关键。" * 6, "en"),
    "en with a few CJK words": ("The word 你好 means hello in Chinese, and 안녕 is the Korean greeting. Both appear in this guide to travel phrases for beginners." * 6, "en"),
    "fr with a few Chinese words": ((FRENCH_LINE + "Le mot 教育 signifie éducation. ") * 5, "fr"),
}

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
        for key, texts in UNSUPPORTED.items():
            for text in texts:
                for label, doc in (("3x", text * 3), ("long", text * 60), ("letter-spaced", letter_spaced(text * 3))):
                    with self.subTest(language=key, text=text[:20], form=label):
                        self.assertEqual(detect_language(doc), "en")

    def test_stress_shapes_never_pick_a_wrong_language(self):
        """Any shape may fall back to English, but must NEVER give another language."""
        import random

        rng = random.Random(7)
        corpus = []
        for k, texts in SLAVIC.items():
            corpus += [(k, t) for t in texts]
        for k, texts in LANES.items():
            corpus += [(LANE_EXPECTED[k], t) for t in texts]
        for k, texts in EXTRA_TEXTS.items():
            corpus += [(k, t) for t in texts]
        corpus += [(k, t) for k, t in SAMPLES.items()] + [("hi", t) for t in HINDI_TEXTS]
        corpus += [("en", t) for texts in UNSUPPORTED.values() for t in texts]
        for want, text in corpus:
            for name, (shape, repeat) in STRESS_SHAPES.items():
                got = detect_language(shape(text * repeat, rng))
                with self.subTest(language=want, shape=name, text=text[:20]):
                    self.assertIn(got, {want, "en"})

    def test_low_content_text_falls_back_to_english(self):
        """A looping OCR transcript has too few distinct words to tell siblings apart."""
        import random

        for code in ("bg", "mk", "sr", "ru", "uk", "cs", "sk", "sv", "ms", "pt"):
            texts = SLAVIC.get(code) or LANES.get(code) or [SAMPLES.get(code) or UNSUPPORTED[code][0]]
            with self.subTest(language=code):
                self.assertEqual(detect_language(_shape_loop(texts[0], random.Random(1))), "en")

    def test_all_caps_documents(self):
        for code in ("pl", "cs", "sk", "sl", "hr", "fi", "et", "tr", "nl", "lt", "es", "da", "ms", "id"):
            text = (SLAVIC.get(code) or LANES.get(code) or [SAMPLES[code]])[0]
            with self.subTest(language=code):
                self.assertEqual(detect_language((text * 4).upper()), code)

    def test_arabic_script_and_scandinavian_tie_breakers(self):
        import langdetect

        real = langdetect.detect
        try:
            for code, siblings in EXTRA_SIBLINGS.items():
                for wrong in siblings:
                    langdetect.detect = lambda text, wrong=wrong: wrong
                    for text in EXTRA_TEXTS[code]:
                        with self.subTest(language=code, forced=wrong, text=text[:20]):
                            self.assertEqual(detect_language(text * 3), code)
        finally:
            langdetect.detect = real

    def test_chinese_simplified_vs_traditional(self):
        for key, want in (("zh", "zh"), ("zh-trad", "zh-tw")):
            doc = " ".join(LANES[key]) * 10
            with self.subTest(script=key):
                self.assertEqual(detect_language(doc), want)
        self.assertEqual(detect_language_name(" ".join(LANES["zh-trad"]) * 10), "Chinese (Traditional) (zh-tw)")

    def test_real_mind_map_upload_is_chinese(self):
        """langdetect called this real upload's text Korean in production."""
        self.assertEqual(detect_language(MIND_MAP_PAGE * 12), "zh")

    def test_hindi_marathi_nepali_overrule_a_wrong_langdetect_call(self):
        import langdetect

        real = langdetect.detect
        try:
            for texts, want in ((HINDI_TEXTS, "hi"), (UNSUPPORTED["mr"], "en"), (UNSUPPORTED["ne"], "en")):
                for forced in ("hi", "mr", "ne"):
                    langdetect.detect = lambda text, forced=forced: forced
                    for text in texts:
                        with self.subTest(want=want, forced=forced, text=text[:20]):
                            self.assertEqual(detect_language(text * 3), want)
        finally:
            langdetect.detect = real

    def test_cjk_and_uralic_lanes(self):
        for key, texts in LANES.items():
            want = LANE_EXPECTED[key]
            for text in texts:
                forms = [("3x", text * 3), ("long", text * 60), ("letter-spaced", letter_spaced(text * 3))]
                if len(text) >= 30:  # shorter than the 30-char minimum is English by design
                    forms.append(("1x", text))
                for label, doc in forms:
                    with self.subTest(language=key, text=text[:20], form=label):
                        self.assertEqual(detect_language(doc), want)

    def test_lane_tie_breakers_overrule_a_wrong_langdetect_call(self):
        """Scripts (CJK) and unique letters/words (Hungarian lane) decide, not langdetect."""
        import langdetect

        real = langdetect.detect
        try:
            for key, siblings in LANE_SIBLINGS.items():
                for wrong in siblings:
                    langdetect.detect = lambda text, wrong=wrong: wrong
                    for text in LANES[key]:
                        with self.subTest(language=key, forced=wrong, text=text[:20]):
                            self.assertEqual(detect_language(text * 3), LANE_EXPECTED[key])
        finally:
            langdetect.detect = real

    def test_mixed_script_documents(self):
        for name, (text, want) in MIXED_SCRIPT_CASES.items():
            with self.subTest(case=name):
                self.assertEqual(detect_language(text), want)

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
