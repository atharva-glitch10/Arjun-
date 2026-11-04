"""Phone apps by voice (Spotify, JioSaavn, YouTube Music, Google Maps): family-approved only, one tap on the page,
never a claim that the app opened. Real core-api in memory; the LLM is a fake provider."""

import pytest
from reasoning_svc.appcmd import OPEN_APP, parse_app_command
from reasoning_svc.apps import detect_app
from tests.test_app_commands import engine, link
from tests.test_llm_policy import Llm, _payload, make_engine


@pytest.fixture()
def apps(core_http, uid):
    for app_id, label in (("spotify", "स्पॉटिफाय"), ("jiosaavn", "जिओसावन"), ("google_maps", "गूगल मॅप्स")):
        link(core_http, uid, kind="app", label=label, value=app_id)


@pytest.mark.parametrize(
    ("text", "app", "query"),
    [
        ("स्पॉटिफायवर लता मंगेशकरची गाणी लाव", "spotify", "लता मंगेशकर गाणी"),
        ("स्पॉटिफाय उघड", "spotify", ""),
        ("जिओसावनवर भजन लाव", "jiosaavn", "भजन"),
        ("मॅप्समध्ये जवळचं मंदिर दाखव", "google_maps", "जवळ मंदिर"),
        ("यूट्यूब म्युझिक लाव", "youtube_music", ""),
        ("open spotify", "spotify", ""),
    ],
)
def test_rules_find_the_app_and_her_search_words(text, app, query):
    cmd = parse_app_command(text)
    assert cmd is not None and cmd.intent == OPEN_APP and cmd.topic == app
    assert cmd.query == query


@pytest.mark.parametrize("text", ["माझा नातू स्पॉटिफाय वापरतो", "मॅप खूप जुना आहे", "यूट्यूबवर भजन लाव"])
def test_a_mention_without_a_request_or_plain_youtube_is_not_a_phone_app(text):
    cmd = parse_app_command(text)
    assert cmd is None or cmd.intent != OPEN_APP


def test_detect_app_matches_case_endings():
    assert detect_app("स्पॉटिफायवर")[0] == "spotify"
    assert detect_app("आज पाऊस आहे") is None


def test_an_approved_app_asks_for_one_tap_and_carries_only_id_and_words(core_http, uid, apps):
    res = engine(core_http).handle(uid, "स्पॉटिफायवर लता मंगेशकरची गाणी लाव")
    assert res.intent == "OPEN_APP"
    assert res.reply == "स्पॉटिफायमध्ये लता मंगेशकर गाणी शोधतो. उघडण्यासाठी स्क्रीनवरचं बटण दाबा."
    assert res.action == {"type": "open", "kind": "app", "value": "spotify", "title": "स्पॉटिफाय",
                          "query": "लता मंगेशकर गाणी"}
    assert "http" not in str(res.action)


def test_open_without_words(core_http, uid, apps):
    res = engine(core_http).handle(uid, "स्पॉटिफाय उघड")
    assert res.reply == "स्पॉटिफाय उघडण्यासाठी स्क्रीनवरचं बटण दाबा."
    assert res.action["query"] == ""


def test_an_app_the_family_did_not_add_never_opens(core_http, uid, apps):
    res = engine(core_http).handle(uid, "यूट्यूब म्युझिक लाव")
    assert res.intent == "OPEN_APP"
    assert res.reply == "यूट्यूब म्युझिक अजून घरच्यांनी जोडलेलं नाही. त्यांना सांगतो."
    assert res.action.get("kind") != "app"


def test_a_named_app_wins_over_the_models_generic_media_guess(core_http, uid, apps):
    llm = Llm(_payload(reply="", intent="media", query="भजन", media_kind="devotional"))
    res = make_engine(core_http, llm).handle(uid, "जिओसावनवर भजन लाव")
    assert res.intent == "OPEN_APP"
    assert res.action["value"] == "jiosaavn" and res.action["query"] == "भजन"


def test_emergency_still_wins_with_an_app_word(core_http, uid, apps):
    res = engine(core_http).handle(uid, "मला हार्ट अटॅक येतोय स्पॉटिफाय बंद कर")
    assert res.mode == "safety"


def test_core_api_accepts_only_known_app_ids(core_http, uid):
    bad = core_http.post(f"/users/{uid}/app-links", json={"kind": "app", "label": "x", "value": "https://evil.example"})
    assert bad.status_code == 422
    ok = core_http.post(f"/users/{uid}/app-links", json={"kind": "app", "label": "स्पॉटिफाय", "value": "Spotify"})
    assert ok.status_code == 201 and ok.json()["value"] == "spotify"
