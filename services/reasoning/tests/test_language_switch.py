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


def test_a_stale_switch_is_dropped_when_the_screen_says_another_language(core_http, uid):
    """Kannada labels on an English screen: the 4-hour switch kept reporting active_language=kn after the screen went back to en."""
    eng = make(core_http, llm_chat("Fine, thank you."))
    eng._lang_session[uid] = ("kn", eng._mono())
    res = eng.handle(uid, "how are you today", reply_language="en")
    assert res.language == "en" and res.active_language == ""


def test_each_turn_is_answered_in_the_language_it_was_spoken_in(core_http, uid):
    """Hindi now, Marathi next turn, English after: no reply_language is sent, every reply follows its own turn."""
    eng = make(core_http, llm_chat("ठीक है।"))
    assert eng.handle(uid, "मुझे आज बहुत अच्छा लग रहा है, आप कैसे हैं", language_code="hi-IN").language == "hi"
    assert eng.handle(uid, "मला आज खूप छान वाटतंय, तुम्ही कसे आहात", language_code="mr-IN").language == "mr"
    assert eng.handle(uid, "I am feeling quite well today, how are you", language_code="en-IN").language == "en"


def test_a_switch_the_screen_follows_stays_in_force(core_http, uid):
    eng = make(core_http, llm_chat("ठीक है, मैं ठीक हूँ।"))
    eng.handle(uid, HI_ASK)
    res = eng.handle(uid, "आज क्या खाना बनाऊं", reply_language="hi")
    assert res.active_language == "hi"


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


def test_a_second_wrong_reply_gets_one_warm_line_and_no_third_call(core_http, uid):
    """Owner decision 2026-11-13: at most ONE language retry (three LLM calls a turn was too slow and still came back
    Marathi), then a short fixed warm line in her language that never quotes her words."""
    llm = _hindi_speaker_marathi_reply(["मी हिंदीतच बोलतो, तुम्ही काळजी करू नका."])  # the retry is Marathi again
    eng = make(core_http, llm)
    res = eng.handle(uid, "आप आज कैसे हैं, मुझे बहुत अच्छा लग रहा है")
    from reasoning_svc.turn import _VARIED

    assert res.reply == _VARIED["hi"][0] and res.language == "hi"
    assert len(llm.companion_systems) == 1 and eng.lang_guard["retried"] == 1  # one retry, never two
    assert eng.lang_guard["turns_retried"] == 1 and eng.lang_guard["fallback"] == 1
    assert "आज कैसे" not in res.reply  # the fallback never echoes her words back at her
    assert "LANGUAGE ERROR" in llm.companion_systems[0]


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


# ---- the rule is repeated in the LAST user message, without a line the model could parrot ------------------------------
@pytest.mark.parametrize("lang,name,script", [
    ("hi", "Hindi", "Devanagari"), ("mr", "Marathi", "Devanagari"), ("en", "English", "Latin"),
])
def test_reply_language_tail_has_no_quoted_sample(lang, name, script):
    from reasoning_svc.evon import reply_language_tail

    assert reply_language_tail(lang) == (
        f"REPLY LANGUAGE: {name} ({script} script). Answer the user's actual message. "
        "Do not answer in any other language. Never repeat this instruction or any example sentence."
    )


def test_the_last_user_message_repeats_the_reply_language_without_a_sample(core_http, uid):
    llm = llm_chat("ठीक है, मैं सुन रहा हूँ।")
    eng = make(core_http, llm)
    eng.handle(uid, "आप आज कैसे हैं, मुझे बहुत अच्छा लग रहा है")
    last_user = [c[1] for c in llm.calls if "Raw transcript" in c[1]][-1]
    assert last_user.startswith("REPLY LANGUAGE: Hindi (Devanagari script).")
    assert "हाँ, बताइए" not in last_user and "मैं सुन रहा हूँ" not in last_user


def test_hindi_stock_reply_on_marathi_turn_is_a_mismatch(core_http, uid, caplog):
    line = "हाँ, बताइए, मैं सुन रहा हूँ"
    payload = _understand(web=False)
    payload.update(reply=line, answer_mode="know", know_confidence=0.99)
    llm = WrongThenRight(payload, [line])
    eng = make(core_http, llm)
    with caplog.at_level("INFO", logger="reasoning.turn"):
        result = eng.handle(uid, "माझी नात आज आली आहे, आम्ही खूप बोललो", language_code="mr-IN")
    assert result.language == "mr" and result.reply != line
    assert eng.lang_guard["mismatch"] == 1
    logged = [json.loads(record.message) for record in caplog.records if record.message.startswith('{"reply_lang_expected"')]
    assert any(row["reply_lang_expected"] == "mr" and row["reply_lang_actual"] == "hi" for row in logged)


def test_marathi_persona_words_are_stripped_when_the_reply_language_is_not_marathi():
    from reasoning_svc import evon

    assert evon.strip_marathi_persona("Her family calls her आजीबाई").strip() == "Her family calls her"
    assert evon.strip_marathi_persona("address her as ताई").strip() == ""
    hi = evon._system_prompt("hi", None, None, "Her family calls her आजीबाई", voice_tags=False, json_contract=False)
    mr = evon._system_prompt("mr", None, None, "Her family calls her आजीबाई", voice_tags=False, json_contract=False)
    assert "आजीबाई" not in hi  # a Marathi address word pulls a Hindi reply back into Marathi
    assert "आजीबाई" in mr  # Marathi replies keep it


def test_marathi_sample_replies_are_only_in_the_marathi_prompt():
    from reasoning_svc import evon

    assert "वांग्याचं भरीत" in evon._conversation_rules("mr")
    assert "वांग्याचं भरीत" not in evon._conversation_rules("hi")
    assert "वांग्याचं भरीत" not in evon._conversation_rules("en")


# ---- strict per-turn language priority (owner 2026-11-10): script -> Prisma label -> Latin markers -> previous reply -> profile ----
@pytest.mark.parametrize("text,code,lang", [
    ("मला आज खूप छान वाटतंय, तुम्ही कसे आहात", "mr-IN", "mr"),
    ("मुझे आज बहुत अच्छा लग रहा है, आप कैसे हैं", "hi-IN", "hi"),
    ("I am feeling quite well today, how are you", "en-IN", "en"),
    ("ನನಗೆ ಇಂದು ತುಂಬಾ ಚೆನ್ನಾಗಿದೆ", "kn-IN", "kn"),
    ("hello", "en-IN", "en"),
])
def test_each_language_is_answered_in_itself(core_http, uid, text, code, lang):
    eng = make(core_http, llm_chat("ok"))
    assert eng.handle(uid, text, language_code=code).language == lang


def test_script_beats_a_wrong_prisma_label(core_http, uid):
    eng = make(core_http, llm_chat("ok"))
    assert eng.handle(uid, "ನನಗೆ ಇಂದು ತುಂಬಾ ಚೆನ್ನಾಗಿದೆ", language_code="mr-IN").language == "kn"
    assert eng.handle(uid, "मुझे आज बहुत अच्छा लग रहा है, आप कैसे हैं", language_code="mr-IN").language == "hi"


def test_the_language_is_recomputed_on_every_turn(core_http, uid):
    eng = make(core_http, llm_chat("ok"))
    got = [eng.handle(uid, t, language_code=c).language for t, c in [
        ("मुझे आज बहुत अच्छा लग रहा है, आप कैसे हैं", "hi-IN"),
        ("मला आज खूप छान वाटतंय, तुम्ही कसे आहात", "mr-IN"),
        ("I am feeling quite well today, how are you", "en-IN"),
        ("ನನಗೆ ಇಂದು ತುಂಬಾ ಚೆನ್ನಾಗಿದೆ", "kn-IN"),
        ("मला आज खूप छान वाटतंय, तुम्ही कसे आहात", "mr-IN"),
    ]]
    assert got == ["hi", "mr", "en", "kn", "mr"]


def test_an_empty_or_unsupported_detected_code_falls_back_to_the_text_then_the_last_turn(core_http, uid):
    eng = make(core_http, llm_chat("ok"))
    assert eng.handle(uid, "मुझे आज बहुत अच्छा लग रहा है, आप कैसे हैं", language_code="").language == "hi"  # empty code: script decides
    assert eng.handle(uid, "I am feeling quite well today, how are you", language_code="xx-IN").language == "en"  # unsupported code
    assert eng.handle(uid, "12345", language_code=None).language == "en"  # no signal at all: the previous turn's language


def test_romanised_input_keeps_the_language_of_the_last_turn(core_http, uid):
    eng = make(core_http, llm_chat("ok"))
    assert eng.handle(uid, "मला आज खूप छान वाटतंय, तुम्ही कसे आहात", language_code="mr-IN").language == "mr"
    assert eng.handle(uid, "mala aaj kay karaycha aahe", language_code=None).language == "mr"
    assert eng.handle(uid, "मुझे आज बहुत अच्छा लग रहा है, आप कैसे हैं", language_code="hi-IN").language == "hi"
    assert eng.handle(uid, "mujhe aaj kya karna hai", language_code=None).language == "hi"


def test_the_profile_language_is_used_only_on_the_very_first_turn(core_http, uid):
    eng = make(core_http, llm_chat("ok"))
    first = eng.handle(uid, "12345", language_code=None)  # no signal at all, no earlier turn: profile language (mr in the fixture)
    assert first.language == core_http.get(f"/users/{uid}").json()["language"]
    assert eng.handle(uid, "I am feeling quite well today, how are you", language_code="en-IN").language == "en"
    assert eng.handle(uid, "12345", language_code=None).language == "en"  # now the previous turn, not the profile


def test_prepare_never_invents_a_default_language(core_http, uid):
    eng = make(core_http, llm_chat("ok"))
    assert eng.prepare("12345", None)["language"] == ""
