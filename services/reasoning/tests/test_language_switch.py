"""2026-11-10: an elder asked in Hindi for Hindi and Arjun answered in Marathi while claiming to speak Hindi.
Spoken language switch (4 languages), the session / permanent / keep-question flow, the reply-language guard (retry,
regenerate, fixed line) and the explicit REPLY LANGUAGE prompt rule. The LLM is mocked."""

import json

import httpx
import pytest
from reasoning_svc import langswitch
from reasoning_svc.langid import classify
from test_web_search import Llm, _understand, make

HI_ASK = "मुझसे हिंदी में बात करना"
SWITCH_CASES = [
    (HI_ASK, "hi", False),
    ("हिंदीत बोला", "hi", False),
    ("मराठीत बोल", "mr", False),
    ("speak English", "en", False),
    ("तमिल में बोलो", "ta", False),
    ("हमेशा हिंदी में बात करना", "hi", True),
    ("आता नेहमी मराठीत बोल", "mr", True),
    ("talk to me in Hindi from now on", "hi", True),
]


def llm_chat(reply):
    payload = _understand(web=False)
    payload.update(reply=reply, answer_mode="know", know_confidence=0.99)
    return Llm(payload)


@pytest.mark.parametrize("text,lang,permanent", SWITCH_CASES)
def test_switch_requests_are_recognised_with_their_permanence(text, lang, permanent):
    assert langswitch.parse(text) == langswitch.Switch(lang, permanent)


@pytest.mark.parametrize("text", ["हिंदी सिनेमा लावा", "मराठी बातम्या लावा", "हिंदीत बोलू नको", "हिंदी में मत बोलो", "आज पाऊस पडेल का", "english news लगाओ"])
def test_things_that_only_mention_a_language_are_not_switches(text):
    assert langswitch.parse(text) is None


@pytest.mark.parametrize("text,lang", [(HI_ASK, "hi"), ("मराठीत बोल", "mr"), ("speak English", "en"), ("तमिल में बोलो", "ta")])
def test_the_switch_is_confirmed_in_the_new_language_and_takes_effect_at_once(core_http, uid, text, lang):
    eng = make(core_http, llm_chat("छान."))
    res = eng.handle(uid, text)
    assert res.intent == "LANGUAGE_SWITCH" and res.mode == "care" and res.language == lang and res.active_language == lang
    assert langswitch.NAMES[lang] in res.reply
    assert classify(res.reply).lang == lang  # the confirmation itself is in the new language, not in Marathi
    if lang == "hi":
        assert res.reply.startswith("ठीक है, अब मैं हिंदी में बात करूंगा")


def test_the_reported_sentence_is_answered_in_hindi_even_with_a_marathi_label_and_profile(core_http, uid):
    """Profile mr, Prisma label mr-IN: the old rules took the label and answered in Marathi."""
    eng = make(core_http, llm_chat("ठीक है, मैं आपसे हिंदी में बात करूंगा।"))
    res = eng.handle(uid, "आप कैसे हैं, मुझसे हिंदी में बात करना", language_code="mr-IN")
    assert res.language == "hi"


def test_after_a_switch_the_next_replies_follow_it_and_the_prompt_says_so_last(core_http, uid):
    llm = llm_chat("ठीक है, मैं ठीक हूँ। आप कैसे हैं?")
    eng = make(core_http, llm)
    eng.handle(uid, HI_ASK)
    res = eng.handle(uid, "आज क्या खाना बनाऊं", language_code="mr-IN")  # even a Marathi label does not undo the switch
    assert res.language == "hi" and res.active_language == "hi"
    system = [c[0] for c in llm.calls if "Return ONLY one JSON object" in c[0]][-1]
    assert system.rstrip().endswith("This holds even if earlier messages in this conversation were in another language.")
    assert "REPLY LANGUAGE (final rule): reply ONLY in Hindi (Devanagari script)" in system


def test_without_a_switch_the_reply_language_is_the_language_of_her_last_utterance(core_http, uid):
    eng = make(core_http, llm_chat("ठीक आहे, मी ठीक आहे."))
    assert eng.handle(uid, "तुम्ही कसे आहात").language == "mr"
    eng2 = make(core_http, llm_chat("ठीक है, मैं ठीक हूँ।"))
    assert eng2.handle(uid, "आप कैसे हैं आज").language == "hi"


# ---- permanent / keep question ---------------------------------------------------------------------------------------
def _user(core_http, uid):
    return core_http.get(f"/users/{uid}").json()


def test_a_permanent_request_saves_the_profile_and_the_recognition_language(core_http, uid):
    eng = make(core_http, llm_chat("छान."))
    res = eng.handle(uid, "हमेशा हिंदी में बात करना")
    u = _user(core_http, uid)
    assert u["language"] == "hi" and u["preferred_languages"] == ["hi"]
    assert langswitch.SAVED["hi"] in res.reply and langswitch.KEEP_Q["hi"] not in res.reply


def test_a_plain_request_asks_once_and_yes_saves_it(core_http, uid):
    eng = make(core_http, llm_chat("छान."))
    res = eng.handle(uid, HI_ASK)
    assert langswitch.KEEP_Q["hi"] in res.reply and _user(core_http, uid)["language"] == "mr"  # not saved yet
    answer = eng.handle(uid, "हाँ")
    assert answer.intent == "LANGUAGE_SWITCH" and answer.reply == langswitch.SAVED["hi"]
    assert _user(core_http, uid)["language"] == "hi" and _user(core_http, uid)["preferred_languages"] == ["hi"]


def test_a_no_keeps_it_for_now_only_and_the_profile_is_untouched(core_http, uid):
    eng = make(core_http, llm_chat("छान."))
    eng.handle(uid, HI_ASK)
    answer = eng.handle(uid, "नहीं")
    assert answer.reply == langswitch.SESSION_ONLY["hi"] and _user(core_http, uid)["language"] == "mr"
    assert eng._active_lang(uid) == "hi"  # still Hindi for this session


def test_the_keep_question_lapses_when_she_says_something_else(core_http, uid):
    eng = make(core_http, llm_chat("ठीक है।"))
    eng.handle(uid, HI_ASK)
    eng.handle(uid, "आज मौसम कैसा है")
    assert eng.handle(uid, "हाँ").intent != "LANGUAGE_SWITCH"
    assert _user(core_http, uid)["language"] == "mr"


def test_every_confirmation_line_exists_in_all_ten_languages_and_in_that_language():
    assert set(langswitch.OK) == set(langswitch.KEEP_Q) == set(langswitch.SAVED) == set(langswitch.SESSION_ONLY) == set(langswitch.NAMES)
    for lang in langswitch.NAMES:
        for line in (langswitch.confirm(lang, False), langswitch.confirm(lang, True)):
            assert langswitch.NAMES[lang] in line and "{" not in line
            assert classify(line).lang == lang, (lang, line)


# ---- the output guard ------------------------------------------------------------------------------------------------
class WrongThenRight(Llm):
    """Understanding answers in the WRONG language; the companion retries answer in `retries` (a list, last one repeats)."""

    def __init__(self, payload, retries):
        super().__init__(payload)
        self.retries, self.companion_systems = list(retries), []

    def __call__(self, req):
        body = json.loads(req.content)
        system = body["messages"][0]["content"]
        if "Return ONLY one JSON object" in system or "SEARCH RESULTS" in system:
            return super().__call__(req)
        self.companion_systems.append(system)
        text = self.retries.pop(0) if len(self.retries) > 1 else self.retries[0]
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def _hindi_speaker_marathi_reply(retries):
    payload = _understand(web=False)
    payload.update(reply="मी तुमच्याशी हिंदीतच बोलतो.", answer_mode="know", know_confidence=0.99)
    return WrongThenRight(payload, retries)


def test_a_reply_in_the_wrong_language_is_retried_once_with_a_stricter_instruction(core_http, uid, caplog):
    llm = _hindi_speaker_marathi_reply(["ठीक है, मैं आपसे हिंदी में ही बात करूंगा।"])
    eng = make(core_http, llm)
    with caplog.at_level("INFO", logger="reasoning.turn"):
        res = eng.handle(uid, "आप आज कैसे हैं, मुझे बहुत अच्छा लग रहा है")
    assert res.language == "hi" and classify(res.reply).lang == "hi"
    assert len(llm.companion_systems) == 1 and eng.lang_guard["mismatch"] == 1 and eng.lang_guard["retried"] == 1
    logged = [json.loads(r.message) for r in caplog.records if r.message.startswith('{"reply_lang_expected"')]
    assert {"reply_lang_expected": "hi", "reply_lang_actual": "mr", "retried": 1, "fixed": True} in logged


def test_if_the_retry_is_still_wrong_it_regenerates_once_more(core_http, uid):
    llm = _hindi_speaker_marathi_reply(["मी हिंदीतच बोलतो, तुम्ही काळजी करू नका.", "ठीक है, मैं हिंदी में ही बोलूँगा, आप चिंता मत कीजिए।"])
    eng = make(core_http, llm)
    res = eng.handle(uid, "आप आज कैसे हैं, मुझे बहुत अच्छा लग रहा है")
    assert classify(res.reply).lang == "hi" and len(llm.companion_systems) == 2 and eng.lang_guard["retried"] == 2
    assert "LANGUAGE ERROR" in llm.companion_systems[0] and "ENTIRE reply" in llm.companion_systems[1]  # each retry is stricter


def test_a_model_that_never_gets_it_right_is_never_shown_or_spoken_in_the_wrong_language(core_http, uid):
    llm = _hindi_speaker_marathi_reply(["मी हिंदीतच बोलतो."])  # every retry is Marathi again
    eng = make(core_http, llm)
    res = eng.handle(uid, "आप आज कैसे हैं, मुझे बहुत अच्छा लग रहा है")
    from reasoning_svc.turn import _VARIED

    assert res.reply == _VARIED["hi"][0]  # a fixed line in HER language
    assert res.reply != "मी तुमच्याशी हिंदीतच बोलतो." and eng.lang_guard["fallback"] == 1
    assert res.language == "hi"


def test_a_reply_in_the_right_language_is_not_retried(core_http, uid):
    llm = llm_chat("ठीक है, मैं आपकी बात सुन रहा हूँ।")
    eng = make(core_http, llm)
    eng.handle(uid, "आप कैसे हैं, आज मौसम बहुत अच्छा है")
    assert eng.lang_guard["checked"] == 1 and eng.lang_guard["mismatch"] == 0
