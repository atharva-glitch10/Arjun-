"""Safety lexicon for Bengali, Gujarati, Kannada, Malayalam, Punjabi, Tamil and Telugu (added 2026-11-09).

Rules only, runs with every other safety check (boundary 8). UNVERIFIED: written without a native speaker or real
ASR output - it must be reviewed before a public demo, exactly like the Marathi / Hindi lexicons in distress.py.
Recall-biased on purpose (a false positive costs a gentle check-in or a family alert; a false negative is unsafe).
These languages are agglutinative, so matching is by STEM (substring) on NFC text, once as written and once with the
spaces removed (speech-to-text spacing varies)."""

import unicodedata

# physical emergency: chest pain, cannot breathe, a fall, fainting / dizziness, bleeding
EMERGENCY_STEMS: tuple[str, ...] = (
    # Tamil
    "நெஞ்சு வலி", "நெஞ்சில் வலி", "நெஞ்சுவலி", "மார்பு வலி", "மூச்சு விட முடியவில்லை", "மூச்சுத் திணறல்", "மூச்சு வரவில்லை",
    "மயக்கம்", "மயங்கி", "கீழே விழுந்த", "விழுந்துவிட்ட", "எழுந்திருக்க முடியவில்லை", "எழ முடியவில்லை", "ரத்தம் வருகிறது", "இரத்தம் வருகிறது",
    # Telugu
    "ఛాతీలో నొప్పి", "ఛాతి నొప్పి", "గుండె నొప్పి", "ఊపిరి ఆడటం లేదు", "ఊపిరి ఆడడం లేదు", "ఊపిరి తీసుకోలేకపోతు", "కళ్లు తిరుగు",
    "కళ్ళు తిరుగు", "స్పృహ తప్ప", "పడిపోయాను", "కింద పడ్డాను", "లేవలేకపోతు", "రక్తం కారుతో", "రక్తం వస్తో",
    # Kannada
    "ಎದೆ ನೋವು", "ಎದೆನೋವು", "ಉಸಿರಾಡಲು ಆಗುತ್ತಿಲ್ಲ", "ಉಸಿರು ಕಟ್ಟು", "ತಲೆ ಸುತ್ತು", "ತಲೆಸುತ್ತು", "ಪ್ರಜ್ಞೆ ತಪ್ಪ", "ಬಿದ್ದುಬಿಟ್ಟೆ",
    "ಬಿದ್ದೆ", "ಏಳಲು ಆಗುತ್ತಿಲ್ಲ", "ರಕ್ತ ಬರುತ್ತಿದೆ", "ರಕ್ತಸ್ರಾವ",
    # Malayalam
    "നെഞ്ചുവേദന", "നെഞ്ച് വേദന", "ശ്വാസം മുട്ട", "ശ്വസിക്കാൻ കഴിയുന്നില്ല", "ശ്വാസം കിട്ടുന്നില്ല", "തലകറക്ക", "ബോധം പോയ",
    "ബോധം കെട്ട", "വീണുപോയി", "ഞാൻ വീണു", "എഴുന്നേൽക്കാൻ കഴിയുന്നില്ല", "രക്തം വരുന്നു", "രക്തസ്രാവ",
    # Bengali
    "বুকে ব্যথা", "বুক ব্যথা", "বুকব্যথা", "শ্বাস নিতে পারছি না", "শ্বাসকষ্ট", "মাথা ঘুরছে", "মাথা ঘুরে", "অজ্ঞান", "পড়ে গেছি",
    "পড়ে গিয়েছি", "উঠতে পারছি না", "রক্ত পড়ছে", "রক্তপাত",
    # Gujarati
    "છાતીમાં દુખાવો", "છાતીમાં દુખે", "છાતીમાં દર્દ", "શ્વાસ લઈ શકતો નથી", "શ્વાસ લઈ શકતી નથી", "શ્વાસ ચડે", "શ્વાસ નથી લેવાતો",
    "ચક્કર આવે", "ચક્કર આવ", "બેભાન", "પડી ગયો", "પડી ગઈ", "ઊભો થઈ શકતો નથી", "ઊભી થઈ શકતી નથી", "લોહી નીકળે", "લોહી વહે",
    # Punjabi
    "ਛਾਤੀ ਵਿੱਚ ਦਰਦ", "ਛਾਤੀ ਵਿਚ ਦਰਦ", "ਛਾਤੀ 'ਚ ਦਰਦ", "ਸਾਹ ਨਹੀਂ ਆ", "ਸਾਹ ਨਹੀਂ ਲੈ", "ਸਾਹ ਲੈਣ ਵਿੱਚ ਮੁਸ਼ਕਲ", "ਚੱਕਰ ਆ", "ਬੇਹੋਸ਼",
    "ਡਿੱਗ ਪਿਆ", "ਡਿੱਗ ਪਈ", "ਡਿੱਗ ਗਿਆ", "ਉੱਠ ਨਹੀਂ ਸਕ", "ਖੂਨ ਵਗ", "ਖੂਨ ਨਿਕਲ",
)

# emotional distress: wants to die, hopeless, afraid, being hurt
DISTRESS_STEMS: tuple[str, ...] = (
    # Tamil
    "சாக வேண்டும்", "சாகணும்", "சாக வேணும்", "வாழ பிடிக்கவில்லை", "வாழ விருப்பம் இல்லை", "உயிரை மாய்த்", "தற்கொலை", "பயமாக இருக்கிறது",
    "யாராவது என்னை அடிக்கிறார்கள்",
    # Telugu
    "చనిపోవాలని", "చావాలని", "బతకాలని లేదు", "బ్రతకాలని లేదు", "ఆత్మహత్య", "భయంగా ఉంది", "నన్ను కొడుతున్నారు",
    # Kannada
    "ಸಾಯಬೇಕು", "ಸಾಯಬೇಕೆನಿಸ", "ಬದುಕಲು ಇಷ್ಟವಿಲ್ಲ", "ಬದುಕಬೇಕೆನಿಸುತ್ತಿಲ್ಲ", "ಆತ್ಮಹತ್ಯೆ", "ಭಯವಾಗುತ್ತಿದೆ", "ನನ್ನನ್ನು ಹೊಡೆಯುತ್ತಾರೆ",
    # Malayalam
    "മരിക്കണം", "മരിക്കാൻ തോന്നുന്നു", "ജീവിക്കാൻ ആഗ്രഹമില്ല", "ജീവിക്കാൻ തോന്നുന്നില്ല", "ആത്മഹത്യ", "പേടിയാകുന്നു", "എന്നെ അടിക്കുന്നു",
    # Bengali
    "মরে যেতে চাই", "মরতে চাই", "বাঁচতে ইচ্ছে করছে না", "বাঁচতে ইচ্ছা করছে না", "আত্মহত্যা", "ভয় লাগছে", "আমাকে মারে",
    # Gujarati
    "મરી જવું છે", "મરવું છે", "જીવવાની ઇચ્છા નથી", "જીવવું નથી", "આત્મહત્યા", "ડર લાગે છે", "મને મારે છે",
    # Punjabi
    "ਮਰਨਾ ਚਾਹੁੰਦਾ", "ਮਰਨਾ ਚਾਹੁੰਦੀ", "ਜਿਊਣ ਦਾ ਮਨ ਨਹੀਂ", "ਜਿਉਣ ਦਾ ਮਨ ਨਹੀਂ", "ਖੁਦਕੁਸ਼ੀ", "ਡਰ ਲੱਗ", "ਮੈਨੂੰ ਮਾਰਦੇ",
)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", (text or "").casefold())


def _hit(text: str, stems: tuple[str, ...]) -> bool:
    spaced = " ".join(_norm(text).split())
    compact = spaced.replace(" ", "")
    return any(s in spaced or s.replace(" ", "") in compact for s in (_norm(x) for x in stems))


def is_emergency(text: str) -> bool:
    return _hit(text, EMERGENCY_STEMS)


def is_distress(text: str) -> bool:
    return _hit(text, DISTRESS_STEMS)
