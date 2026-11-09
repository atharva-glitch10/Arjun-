"""All ten Gnani languages: script detection, fixed templates, the localized safety lines and the safety lexicon.
The new-language wording is UNVERIFIED by a native speaker; these tests check structure and routing, not translation."""

import re
import unicodedata

import pytest
from reasoning_svc import distress, replies, replies_langs, safety_langs
from reasoning_svc import turn as turn_mod
from reasoning_svc.textutil import detect_language, script_language
from test_web_search import Llm, _understand, make

NEW = ("bn", "gu", "kn", "ml", "pa", "ta", "te")
EMERGENCY = {
    "ta": "எனக்கு நெஞ்சு வலி", "te": "నాకు ఛాతీలో నొప్పి ఉంది", "kn": "ನನಗೆ ಎದೆ ನೋವು", "ml": "എനിക്ക് നെഞ്ചുവേദന",
    "bn": "আমার বুকে ব্যথা", "gu": "મને છાતીમાં દુખાવો", "pa": "ਮੈਨੂੰ ਛਾਤੀ ਵਿੱਚ ਦਰਦ ਹੈ",
}
DISTRESS = {
    "ta": "நான் சாக வேண்டும்", "te": "నేను చనిపోవాలని ఉంది", "kn": "ನನಗೆ ಸಾಯಬೇಕು", "ml": "എനിക്ക് മരിക്കണം",
    "bn": "আমি মরতে চাই", "gu": "મારે મરવું છે", "pa": "ਮੈਂ ਮਰਨਾ ਚਾਹੁੰਦਾ ਹਾਂ",
}
HARMLESS = {
    "ta": "எனக்கு பசிக்கிறது", "te": "నాకు ఆకలిగా ఉంది", "kn": "ನನಗೆ ಹಸಿವು", "ml": "എനിക്ക് വിശക്കുന്നു",
    "bn": "আজ আবহাওয়া কেমন", "gu": "આજે હવામાન કેવું", "pa": "ਅੱਜ ਮੌਸਮ ਕਿਵੇਂ",
}


@pytest.mark.parametrize("lang", NEW)
def test_every_key_exists_with_the_same_placeholders_as_english(lang):
    en, loc = replies.R["en"], replies.R[lang]
    assert set(en) <= set(loc)
    for key, line in en.items():
        assert set(re.findall(r"\{(\w+)\}", loc[key])) == set(re.findall(r"\{(\w+)\}", line)), (lang, key)


@pytest.mark.parametrize("lang", NEW)
def test_core_lines_are_really_in_that_language_not_english_or_marathi(lang):
    for key in replies_langs.TR[lang]:
        assert replies.R[lang][key] != replies.R["en"][key], (lang, key)  # translated, not the English fallback
        assert replies.R[lang][key] != replies.R["mr"][key], (lang, key)
    assert len(replies.WEEKDAYS[lang]) == 7 and len(replies.MONTHS[lang]) == 12
    assert replies.lang_or_default(lang) == lang


@pytest.mark.parametrize("lang,text", [(k, v) for k, v in {**EMERGENCY, **HARMLESS}.items()])
def test_script_alone_decides_the_language(lang, text):
    assert script_language(text) == lang and detect_language(text, "mr") == lang


def test_devanagari_and_latin_are_left_to_the_word_lists():
    assert script_language("आज पाऊस पडेल का") is None and script_language("what is the time") is None
    assert detect_language("what is the time", "mr") == "en"


@pytest.mark.parametrize("lang", NEW)
def test_safety_lexicon_flags_emergency_and_distress_and_not_ordinary_talk(lang):
    assert distress.is_emergency(EMERGENCY[lang]) and safety_langs.is_emergency(EMERGENCY[lang])
    assert distress.is_distress(DISTRESS[lang])
    assert not distress.is_emergency(HARMLESS[lang]) and not distress.is_distress(HARMLESS[lang])


@pytest.mark.parametrize("lang", NEW)
def test_an_emergency_in_her_language_gets_the_fixed_line_in_that_language(core_http, uid, lang):
    core_http.patch(f"/users/{uid}", json={"language": lang})
    res = make(core_http, Llm(_understand(web=False))).handle(uid, EMERGENCY[lang], language_code=f"{lang}-IN")
    assert res.intent == "EMERGENCY" and res.mode == "safety" and res.language == lang
    assert res.reply in (replies_langs.safety_reply(lang, "emergency", True), replies_langs.safety_reply(lang, "emergency", False))
    assert "112" in "".join(str(unicodedata.decimal(c, c)) for c in res.reply)  # 112 in any digit system


@pytest.mark.parametrize("lang", NEW)
def test_distress_in_her_language_is_a_fixed_template_too(core_http, uid, lang):
    core_http.patch(f"/users/{uid}", json={"language": lang})
    res = make(core_http, Llm(_understand(web=False))).handle(uid, DISTRESS[lang], language_code=f"{lang}-IN")
    assert res.intent == "DISTRESS" and res.mode == "safety" and res.language == lang
    assert res.reply in (replies_langs.safety_reply(lang, "distress", True), replies_langs.safety_reply(lang, "distress", False))


@pytest.mark.parametrize("lang", NEW)
def test_medicine_questions_in_every_language_never_reach_the_web(lang):
    words = {"ta": "மருந்து", "te": "మందు", "kn": "ಔಷಧ", "ml": "മരുന്ന്", "bn": "ওষুধ", "gu": "દવા", "pa": "ਦਵਾਈ"}
    assert turn_mod._WEB_BLOCK.search(f"இது {words[lang]} பற்றி")


@pytest.mark.parametrize("lang", NEW)
def test_a_reminder_question_in_her_language_is_answered_in_her_language(core_http, uid, lang):
    core_http.patch(f"/users/{uid}", json={"language": lang})
    res = make(core_http, Llm(_understand(web=False))).handle(uid, HARMLESS[lang], language_code=f"{lang}-IN")
    assert res.language == lang  # no KeyError, no silent switch to Marathi
