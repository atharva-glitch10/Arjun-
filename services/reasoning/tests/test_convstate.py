"""Conversation state (2026-11-10): topic, entities, pending question, references, the capped fixed-order prompt."""

from datetime import datetime, timedelta

from reasoning_svc import config
from reasoning_svc.convstate import (
    ConvState,
    StateTracker,
    est_tokens,
    extract_entities,
    fit_prompt,
    is_short_answer,
)
from test_web_search import NOW, Llm, _understand, make

T0 = datetime(2026, 10, 6, 9, 0)


# ---- entities ---------------------------------------------------------------------------------------------------
def test_people_places_times_are_found():
    e = extract_entities("माझा नातू आर्यन उद्या सकाळी १० वाजता पुण्याला येणार आहे")
    assert "grandson आर्यन" in e["people"] and "उद्या" in e["times"] and "सकाळी" in e["times"] and any("पुण्या" in p for p in e["places"])


def test_english_and_hindi_relations_and_a_capitalised_name():
    assert "wife" in extract_entities("my wife is cooking today")["people"]
    assert "daughter" in extract_entities("मेरी बेटी आज आई थी")["people"]
    assert "Ramesh" in extract_entities("today Ramesh came home")["people"]


def test_a_medicine_is_only_a_flag_never_a_name():
    e = extract_entities("मी आज Metformin गोळी घेतली")
    assert e["medicines"] == ["medicine"]
    t = StateTracker()
    t.update(1, T0, "मी आज Metformin गोळी घेतली", "ठीक आहे.")
    st = t.get(1)
    blob = " ".join([st.topic, st.prev_topic, *st.people, *st.places, *st.times, t.block(1, "हो")])
    assert "Metformin" not in blob and st.medicine_talk


# ---- short answers, topic, pronouns ------------------------------------------------------------------------------
def test_short_answers_are_recognised():
    for w in ("हो", "नाही", "तेच", "आणखी", "yes", "हो हो", "अजून"):
        assert is_short_answer(w), w
    assert not is_short_answer("आज मी बागेत गेले")


def test_a_short_answer_does_not_change_the_topic_but_a_new_subject_does():
    t = StateTracker()
    t.update(1, T0, "माझा नातू आर्यन उद्या येणार आहे", "छान.")
    topic = t.get(1).topic
    assert "आर्यन" in topic
    t.update(1, T0, "हो", "बरं.")
    assert t.get(1).topic == topic
    t.update(1, T0, "आज मी भाजी आणायला बाजारात गेले होते", "छान.")
    assert t.get(1).topic != topic and t.get(1).prev_topic == topic  # she changed the subject: follow her


def test_a_pronoun_points_at_the_last_person_named():
    t = StateTracker()
    t.update(1, T0, "माझा नातू आर्यन उद्या येणार आहे", "छान.")
    refs = t.references(1, "त्याला काय आवडतं")
    assert refs and "आर्यन" in refs[0]
    assert "त्याला" in t.block(1, "त्याला काय आवडतं")


def test_a_pronoun_with_nothing_before_it_asks_for_one_short_question():
    t = StateTracker()
    refs = t.references(1, "त्याला काय आवडतं")
    assert refs == []  # no state yet: the model gets no false antecedent
    t.update(1, T0, "आज ऊन आहे", "हो.")
    assert "ask ONE short question" in t.references(1, "ती कुठे आहे")[0]  # no person: only the topic is offered, with a way out
    t.reset(1)
    t.get(1)
    assert "nothing before it" in t.references(1, "ती कुठे आहे")[0]


def test_a_short_answer_gets_a_reference_line():
    t = StateTracker()
    t.update(1, T0, "आज मी भजन ऐकलं", "आणखी भजन लावू का?")
    assert "SHORT ANSWER" in t.block(1, "हो")


def test_state_keeps_only_the_last_six_exchanges_and_resets_after_silence():
    t = StateTracker(idle_min=30)
    for i in range(9):
        t.update(1, T0, f"आज मी बागेत गेले होते {i}", "छान.")
    assert len(t.get(1).turns) == 6
    t.update(1, T0 + timedelta(minutes=45), "आज मी स्वयंपाक केला", "छान.")
    assert len(t.get(1).turns) == 1  # a new conversation


def test_forget_scrubs_the_state():
    t = StateTracker()
    t.update(1, T0, "लक्षात ठेव सकाळी तुळशीची पूजा", "ठीक आहे.")
    t.scrub(1, "सकाळी तुळशीची पूजा")
    st = t.get(1)
    assert not st.turns and "तुळशी" not in st.topic and not st.times


# ---- the capped, fixed-order prompt ------------------------------------------------------------------------------
def msgs(n):
    out = []
    for i in range(n):
        out += [("user", f"आज मी बागेत गेले होते आणि फुलं पाहिली {i}"), ("assistant", f"छान वाटलं ऐकून {i}.")]
    return out


def test_fit_prompt_never_drops_the_open_question_or_the_last_two_exchanges():
    pending = "OPEN QUESTION: you (Arjun) just asked: \"भजन लावू का?\"\n"
    m, memory, ctx, info = fit_prompt(
        messages=msgs(10), block_memory=pending, block_state="CONVERSATION STATE:\n- current topic: भजन\n- people mentioned: a\n- x\n",
        context_base="BASE " * 20, facts=[f"- fact {i} " + "शब्द " * 30 for i in range(10)], facts_header="FACTS", cap_tokens=60,
    )
    assert "OPEN QUESTION" in memory and m[-4:] == msgs(10)[-4:] and m[0][0] == "user"
    assert info["facts"] == 10 and info["messages"] > 0 and ctx.startswith("BASE")


def test_fit_prompt_drops_facts_before_history_and_keeps_everything_when_it_fits():
    m, memory, ctx, info = fit_prompt(
        messages=msgs(6), block_memory="", block_state="", context_base="BASE", facts=["- a", "- b", "- c"], facts_header="F", cap_tokens=10_000,
    )
    assert len(m) == 12 and info["facts"] == 0 and "- c" in ctx
    base_total = est_tokens("BASE") + sum(est_tokens(t) for _, t in msgs(6)) + est_tokens("F\n- a\n- b\n- c")
    m, _, ctx, info = fit_prompt(
        messages=msgs(6), block_memory="", block_state="", context_base="BASE", facts=["- a", "- b", "- c"], facts_header="F", cap_tokens=base_total - 3,
    )
    assert info["facts"] >= 1 and info["messages"] == 0 and len(m) == 12  # a fact went first, no turn was lost


def test_history_sent_starts_with_her_and_is_at_most_six_exchanges():
    m, *_ = fit_prompt(messages=[("assistant", "प्रश्न?"), *msgs(9)], block_memory="", block_state="", context_base="", facts=[], facts_header="", cap_tokens=99999)
    assert m[0][0] == "user" and len(m) <= 12


# ---- in the real engine ------------------------------------------------------------------------------------------
def prompt_of(llm):
    return [c[0] for c in llm.calls if "Return ONLY one JSON object" in c[0]][-1]


def test_the_llm_prompt_carries_the_state_and_the_pronoun_reference(core_http, uid):
    llm = Llm(_understand(web=False))
    eng = make(core_http, llm)
    eng.handle(uid, "माझा नातू आर्यन उद्या येणार आहे")
    eng.handle(uid, "त्याला काय आवडतं")
    system = prompt_of(llm)
    assert "CONVERSATION STATE" in system and "current topic" in system and "आर्यन" in system and '"त्याला" most likely means' in system


def test_the_state_follows_a_change_of_subject_in_the_real_engine(core_http, uid):
    llm = Llm(_understand(web=False))
    eng = make(core_http, llm)
    eng.handle(uid, "माझा नातू आर्यन उद्या येणार आहे")
    eng.handle(uid, "आज मी भाजी आणायला बाजारात गेले होते")
    st = eng.convstate.get(uid)
    assert "बाजार" in st.topic and "आर्यन" in st.prev_topic


def test_the_open_question_survives_a_tiny_cap_in_the_real_engine(core_http, uid, monkeypatch):
    monkeypatch.setattr(config, "PROMPT_TOKEN_CAP", 50)
    llm = Llm(_understand(web=False))
    eng = make(core_http, llm)
    eng.memory.arjun_said(uid, NOW, "आज भजन लावू का?", "checkin")
    eng.handle(uid, "तेच")
    assert "OPEN QUESTION" in prompt_of(llm) and eng.last_prompt_info[uid]["facts"] >= 0


def test_the_switch_restores_the_old_assembly(core_http, uid, monkeypatch):
    monkeypatch.setattr(config, "CONTEXT_STATE", False)
    llm = Llm(_understand(web=False))
    eng = make(core_http, llm)
    eng.handle(uid, "माझा नातू आर्यन उद्या येणार आहे")
    eng.handle(uid, "त्याला काय आवडतं")
    assert "CONVERSATION STATE" not in prompt_of(llm)


def test_convstate_dataclass_defaults():
    st = ConvState()
    assert st.topic == "" and st.turns == [] and not st.medicine_talk
