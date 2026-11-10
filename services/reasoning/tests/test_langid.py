"""The shared language classifier: Marathi vs Hindi (both Devanagari), other scripts, English, code-mixing, and that the three
copies (shared/, reasoning, voice-agent) never drift apart."""

from pathlib import Path

import pytest
from reasoning_svc.langid import Guess, classify, confident, matches

MARATHI = [
    "मी तुमच्याशी हिंदीतच बोलतो", "आज काय चाललंय तुमचं", "मला औषध घ्यायचं आहे", "तुम्ही कसे आहात", "माझं डोकं दुखतंय", "उद्या सकाळी डॉक्टरांकडे जायचं आहे",
    "आज मी बागेत फिरायला गेलो होतो", "तुम्हाला काय हवं आहे", "नाही, मला आत्ता नको", "तुमच्या मुलाला फोन लावतो", "मला भजन ऐकायचं आहे",
    "आज पाऊस पडेल का", "मी जेवण केलं आणि थोडा आराम केला", "काय सांगता, खरंच का", "तुम्ही काळजी करू नका, सगळं ठीक होईल",
    "माझी नात आज येणार आहे", "बरं मग आता काय करायचं", "होय, मला खूप आवडतं", "आम्ही उद्या गावी जातोय", "तुला काय पाहिजे",
    "मला तुमची आठवण येते", "आता मी झोपतो", "तुम्ही मला काय विचारलं", "सकाळी मी चहा घेतला", "ते कधी येणार आहेत",
    "माझ्या मुलाचं नाव राहुल आहे", "आज खूप छान वाटतंय", "मी मराठीत बोलतो, तुम्हीही मराठीत बोला", "बाहेर थंडी आहे का", "त्यांना सांगा की मी ठीक आहे",
    # code-mixed with English words / names
    "मला doctor कडे जायचं आहे", "आज WhatsApp वर फोटो आला आहे", "मी YouTube वर भजन ऐकतो", "Rahul ला फोन लाव", "माझा phone कुठे आहे",
]
HINDI = [
    "मुझसे हिंदी में बात करना", "आप कैसे हैं", "मुझे दवा लेनी है", "आज क्या चल रहा है", "मेरा सिर दर्द कर रहा है", "कल सुबह डॉक्टर के पास जाना है",
    "आज मैं बगीचे में टहलने गया था", "आपको क्या चाहिए", "नहीं, मुझे अभी नहीं चाहिए", "आपके बेटे को फोन लगाता हूँ", "मुझे भजन सुनना है",
    "आज बारिश होगी क्या", "मैंने खाना खाया और थोड़ा आराम किया", "क्या बात है, सच में", "आप चिंता मत कीजिए, सब ठीक हो जाएगा",
    "मेरी पोती आज आने वाली है", "ठीक है, अब क्या करना है", "हाँ, मुझे बहुत पसंद है", "हम कल गाँव जा रहे हैं", "तुम्हें क्या चाहिए",
    "मुझे आपकी याद आती है", "अब मैं सोता हूं", "आपने मुझसे क्या पूछा", "सुबह मैंने चाय पी", "वे कब आएंगे",
    "मेरे बेटे का नाम राहुल है", "आज बहुत अच्छा लग रहा है", "मैं हिंदी में बोलता हूँ, आप भी हिंदी में बोलिए", "बाहर ठंड है क्या", "उन्हें बताइए कि मैं ठीक हूँ",
    # code-mixed with English words / names
    "मुझे doctor के पास जाना है", "आज WhatsApp पर फोटो आई है", "मैं YouTube पर भजन सुनता हूँ", "Rahul को फोन लगाओ", "मेरा phone कहाँ है",
]


@pytest.mark.parametrize("text", MARATHI)
def test_marathi_sentences_are_marathi(text):
    g = classify(text)
    assert g.lang == "mr", (text, g)


@pytest.mark.parametrize("text", HINDI)
def test_hindi_sentences_are_hindi(text):
    g = classify(text)
    assert g.lang == "hi", (text, g)


def test_the_reported_bug_sentence_is_hindi_and_the_wrong_reply_is_marathi():
    asked = classify("मुझसे हिंदी में बात करना")
    answered = classify("मी तुमच्याशी हिंदीतच बोलतो")
    assert (asked.lang, answered.lang) == ("hi", "mr") and confident(asked) and confident(answered)
    assert not matches("मी तुमच्याशी हिंदीतच बोलतो", "hi")  # the output guard would have caught it
    assert matches("ठीक है, अब मैं हिंदी में बात करूंगा", "hi")


def test_other_scripts_english_and_empty():
    assert classify("எனக்கு மருந்து வேண்டும்").lang == "ta" and classify("నాకు మందు కావాలి").lang == "te"
    assert classify("ನನಗೆ ಔಷಧ ಬೇಕು").lang == "kn" and classify("എനിക്ക് മരുന്ന് വേണം").lang == "ml"
    assert classify("আমার ওষুধ লাগবে").lang == "bn" and classify("મને દવા જોઈએ છે").lang == "gu"
    assert classify("ਮੈਨੂੰ ਦਵਾਈ ਚਾਹੀਦੀ ਹੈ").lang == "pa"
    assert classify("Please speak English with me").lang == "en"
    assert classify("") == Guess("", 0.0) and classify("123 !!!").lang == ""


def test_a_tie_uses_the_default_label():
    assert classify("आज", default="hi").lang == "hi" and classify("आज", default="mr").lang == "mr"
    assert classify("आज").confidence == 0.0 and not confident(classify("आज"))


def test_matches_is_forgiving_about_names_and_short_text():
    assert matches("ठीक आहे, Rahul ला फोन लावतो", "mr")
    assert matches("ठीक है", "hi") and matches("ठीक है", "mr")  # shared words: not a mismatch
    assert matches("Okay", "en") and not matches("Okay, I will call him now", "hi")
    assert not matches("நான் உங்களுடன் பேசுகிறேன்", "mr")


def test_the_three_copies_are_identical():
    root = Path(__file__).resolve().parents[3]
    shared = (root / "shared" / "langid.py").read_bytes()
    assert (root / "services" / "reasoning" / "reasoning_svc" / "langid.py").read_bytes() == shared
    assert (root / "services" / "voice-agent" / "langid.py").read_bytes() == shared
