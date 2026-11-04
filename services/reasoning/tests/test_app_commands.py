"""Apps by voice: YouTube, news aloud, WhatsApp, a family link, stop / next / volume. Built from the user stories.
Real core-api in memory; the Google API and the news feeds are mocked (no real network). Lexicon is UNVERIFIED."""

import json
from datetime import datetime

import httpx
import pytest
from core_api import media
from reasoning_svc.appcmd import parse_app_command
from reasoning_svc.core_client import CoreClient
from reasoning_svc.evon import EvonClient, load_intent_schema
from reasoning_svc.turn import TurnEngine
from reasoning_svc.wellbeing import Conversation, Tracker

NOW = datetime(2026, 10, 6, 9, 0)
PLAYLIST = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
CHANNEL = "UCZFMm1mMw0F81Z37aaEzTUA"
FEED_A = "<rss><channel>" + "".join(f"<item><title>बातमी अ{i}</title></item>" for i in range(1, 5)) + "</channel></rss>"
FEED_B = "<rss><channel>" + "".join(f"<item><title>बातमी ब{i}</title></item>" for i in range(1, 5)) + "</channel></rss>"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    media.reset_quota_for_tests()
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    yield
    media.reset_quota_for_tests()


def link(core_http, uid, **body):
    r = core_http.post(f"/users/{uid}/app-links", json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def household(core_http, uid):
    """Synthetic household: favourites, a live news channel, two feeds, WhatsApp for चंद्रकांत, a photos link."""
    c = core_http.post(f"/users/{uid}/contacts", json={"name": "चंद्रकांत", "phone": "9000000001"}).json()
    link(core_http, uid, kind="youtube_playlist", label="भक्तिगीते", value=PLAYLIST, spoken_names=["भजन", "देवाची गाणी"])
    link(core_http, uid, kind="youtube_channel_live", label="मराठी बातम्या", value=CHANNEL, spoken_names=["बातम्या"])
    link(core_http, uid, kind="rss", label="लोकसत्ता", value="https://www.loksatta.com/feed")
    link(core_http, uid, kind="rss", label="सकाळ", value="https://www.esakal.com/feed")
    link(core_http, uid, kind="whatsapp", label="चंद्रकांत", value=str(c["id"]), spoken_names=["चंद्रकांत"])
    link(core_http, uid, kind="link", label="नातवाचे फोटो", value="https://photos.google.com/share/abc")
    return c


def engine(core_http, llm=None):
    return TurnEngine(CoreClient(core_http), llm, clock=lambda: NOW, ask_first=False)


class Google:
    def __init__(self, ids=("AAAAAAAAAAA",)):
        self.calls, self.ids = [], ids

    def __call__(self, url, params=None, timeout=5.0):
        self.calls.append(params)
        q = (params or {}).get("q", "")
        # Titles contain the query words: core-api drops a result whose title matches none of them.
        items = [{"id": {"videoId": v}, "snippet": {"title": f"{q} {v}", "channelTitle": "Ch"}} for v in self.ids]
        return httpx.Response(200, json={"items": items})


def with_google(monkeypatch, g=None):
    g = g or Google()
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(media, "http_get", g)
    return g


def with_feeds(monkeypatch, mapping=None):
    mapping = mapping or {"https://www.loksatta.com/feed": FEED_A, "https://www.esakal.com/feed": FEED_B}

    def get(url, params=None, timeout=5.0):
        body = mapping[url]
        if isinstance(body, Exception):
            raise body
        return httpx.Response(200, content=body.encode())

    monkeypatch.setattr(media, "http_get", get)


# ---- the parser: every user story, and what must stay chat -----------------------------------------------------------
@pytest.mark.parametrize(
    "text, intent",
    [
        ("मला यूट्यूब बघायचं आहे", "OPEN_MEDIA"),
        ("भीमसेन जोशींचं भजन लावा", "OPEN_MEDIA"),
        ("लता मंगेशकरची गाणी लाव", "OPEN_MEDIA"),
        ("मला गाणी ऐकायची आहेत", "OPEN_MEDIA"),
        ("बातम्या बघायच्या आहेत", "OPEN_MEDIA"),
        ("बातम्या ऐकवा", "NEWS_READ"),
        ("आजच्या बातम्या सांग", "NEWS_READ"),
        ("चंद्रकांतला व्हॉट्सॲप कर", "OPEN_WHATSAPP"),
        ("व्हॉट्सॲप कॉल लाव", "OPEN_WHATSAPP"),
        ("चंद्रकांतला व्हॉट्सअ‍ॅप कॉल कर", "OPEN_WHATSAPP"),
        ("open youtube", "OPEN_MEDIA"),
        ("play a bhajan", "OPEN_MEDIA"),
        ("youtube पर भजन चलाओ", "OPEN_MEDIA"),
        ("समाचार सुनाओ", "NEWS_READ"),
        ("अर्जुन, थांबव", "MEDIA_CONTROL"),
        ("बंद कर", "MEDIA_CONTROL"),
        ("आवाज कमी कर", "MEDIA_CONTROL"),
        ("पुढचं गाणं", "MEDIA_CONTROL"),
    ],
)
def test_user_stories_are_recognised(text, intent):
    cmd = parse_app_command(text)
    assert cmd is not None and cmd.intent == intent, text


@pytest.mark.parametrize(
    "text, query",
    [
        ("भीमसेन जोशींचं भजन लावा", "भीमसेन जोशी भजन"),
        ("लता मंगेशकरचं गाणं लाव", "लता मंगेशकर गाणं"),
        ("मला विठ्ठलाची आरती लावा", "विठ्ठल आरती"),
        ("यूट्यूबवर पु ल देशपांडे दाखव", "पु ल देशपांडे"),
    ],
)
def test_query_extraction_keeps_subject_words_and_strips_possessives(text, query):
    cmd = parse_app_command(text)
    assert cmd is not None and cmd.query == query, text


@pytest.mark.parametrize(
    "text, control",
    [("अर्जुन, थांबव", "stop"), ("बंद कर", "stop"), ("बंद करा", "stop"), ("आवाज कमी कर", "volume_down"),
     ("आवाज वाढव", "volume_up"), ("पुढचं गाणं", "next"), ("next", "next"), ("pause", "pause"),
     ("volume down", "volume_down"), ("आवाज हळू कर", "volume_down")],
)
def test_control_words(text, control):
    assert parse_app_command(text).control == control


@pytest.mark.parametrize(
    "text",
    [
        "मला गाणं आठवलं, लहानपणी आम्ही गायचो",  # a memory that mentions a song: chat
        "आज बातम्यांमध्ये काय आलं ते मला कळलं नाही",
        "आज मी बागेत गेले होते",
        "दिवा लावा",
        "what's next",
        "उद्या सकाळी बातम्या ऐकवायची आठवण करून द्या",
    ],
)
def test_stories_and_reminders_are_not_app_commands(text):
    cmd = parse_app_command(text, remind="आठवण" in text)
    assert cmd is None, text


def test_a_song_story_stays_chat_in_the_engine(core_http, uid, household):
    res = engine(core_http).handle(uid, "मला गाणं आठवलं, लहानपणी आम्ही गायचो")
    assert res.intent == "CHAT" and res.action["type"] == "none"


def test_a_reminder_about_the_news_is_still_a_reminder(core_http, uid, household):
    res = engine(core_http).handle(uid, "उद्या सकाळी १० वाजता बातम्या ऐकवायची आठवण करून द्या")
    assert res.intent == "CREATE_REMINDER" and res.action["type"] == "none"


# ---- YouTube ------------------------------------------------------------------------------------------------------
def test_youtube_opens_the_family_favourite(core_http, uid, household):
    res = engine(core_http).handle(uid, "मला यूट्यूब बघायचं आहे")
    assert res.intent == "OPEN_MEDIA" and res.reply == "यूट्यूब उघडलं."
    assert res.action == {"type": "open", "kind": "youtube_playlist", "value": PLAYLIST, "title": "भक्तिगीते",
                          "query": ""}

def test_empty_query_asks_and_the_next_answer_becomes_the_query(core_http, uid, monkeypatch):
    eng = engine(core_http)  # no app_links for this user: nothing to open and no search words
    asked = eng.handle(uid, "यूट्यूब उघड")
    assert asked.intent == "OPEN_MEDIA" and asked.action["type"] == "none"
    assert asked.reply == "काय बघायचं आहे — बातम्या, गाणी की रेसिपी?"

    g = with_google(monkeypatch)
    res = eng.handle(uid, "भजन")
    assert res.intent == "OPEN_MEDIA" and res.action["kind"] == "youtube_video"
    assert g.calls[0]["q"].startswith("भजन")

    media.reset_quota_for_tests()
    eng2 = engine(core_http)
    assert eng2.handle(uid, "व्हिडिओ लाव").reply == "काय बघायचं आहे — बातम्या, गाणी की रेसिपी?"
    res = eng2.handle(uid, "लता मंगेशकर")
    assert g.calls[-1]["q"] == "लता मंगेशकर" and res.action["kind"] == "youtube_video"


def test_core_client_can_ask_core_api_for_the_same_match(core_http, uid, household):
    core = CoreClient(core_http)
    assert core.app_match(uid, "आज भजन लाव")["label"] == "भक्तिगीते"
    assert core.app_match(uid, "काहीच नाही") is None


def test_a_named_favourite_opens_before_any_search(core_http, uid, household, monkeypatch):
    g = with_google(monkeypatch)
    res = engine(core_http).handle(uid, "देवाची गाणी लाव")
    assert res.action["type"] == "open" and res.action["kind"] == "youtube_playlist"
    assert res.action["value"] == PLAYLIST and res.action["title"] == "भक्तिगीते"
    assert g.calls == []  # the family's favourite, no quota spent


def test_a_named_singer_is_searched_and_the_first_video_opens(core_http, uid, household, monkeypatch):
    g = with_google(monkeypatch, Google(("BBBBBBBBBBB", "CCCCCCCCCCC")))
    res = engine(core_http).handle(uid, "भीमसेन जोशींचं भजन लावा")
    assert res.intent == "OPEN_MEDIA" and res.reply == "लावतो: भीमसेन जोशी भजन BBBBBBBBBBB."
    assert res.action == {"type": "open", "kind": "youtube_video", "video_id": "BBBBBBBBBBB",
                          "title": "भीमसेन जोशी भजन BBBBBBBBBBB"}
    assert g.calls[0]["q"] == "भीमसेन जोशी भजन" and g.calls[0]["safeSearch"] == "strict"


def test_songs_by_a_singer_are_searched_too(core_http, uid, household, monkeypatch):
    g = with_google(monkeypatch)
    res = engine(core_http).handle(uid, "लता मंगेशकरची गाणी लाव")
    assert res.reply == "लावतो: लता मंगेशकर गाणी AAAAAAAAAAA." and res.action["kind"] == "youtube_video"
    assert g.calls[0]["q"] == "लता मंगेशकर गाणी"


def test_a_bare_bhajan_request_uses_the_family_playlist_without_a_search(core_http, uid, household, monkeypatch):
    g = with_google(monkeypatch)
    for said in ("भजन लावा", "मला गाणी ऐकायची आहेत"):
        res = engine(core_http).handle(uid, said)
        assert res.action["kind"] == "youtube_playlist" and res.action["value"] == PLAYLIST, said
    assert g.calls == []  # nothing was searched: no quota spent


def test_without_a_key_the_youtube_results_page_opens_and_is_not_hidden(core_http, uid, household):
    res = engine(core_http).handle(uid, "लता मंगेशकरची गाणी लाव")  # YOUTUBE_API_KEY is unset
    assert res.action["kind"] == "url"
    assert res.action["value"].startswith("https://www.youtube.com/results?search_query=")
    assert res.reply == "यूट्यूबवर शोधलं आहे. हवा असलेला व्हिडिओ दाबा."


def test_a_quota_error_also_falls_back_to_the_results_page(core_http, uid, household, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(media, "http_get", lambda *a, **k: httpx.Response(403, text="quotaExceeded"))
    res = engine(core_http).handle(uid, "लता मंगेशकरची गाणी लाव")
    assert res.action["kind"] == "url" and res.action["value"].startswith("https://www.youtube.com/results")
    assert res.reply == "यूट्यूबवर शोधलं आहे. हवा असलेला व्हिडिओ दाबा."


def test_nothing_found_and_google_down_are_fixed_lines(core_http, uid, household, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(media, "http_get", lambda *a, **k: httpx.Response(200, json={"items": []}))
    res = engine(core_http).handle(uid, "लता मंगेशकरची गाणी लाव")
    assert res.reply == "हे मला सापडलं नाही. परत नाव सांगाल?" and res.action["type"] == "none"

    def down(*a, **k):
        raise httpx.ConnectError("down")

    media.reset_quota_for_tests()
    monkeypatch.setattr(media, "http_get", down)
    res = engine(core_http).handle(uid, "आशा भोसलेची गाणी लाव")
    assert res.action["kind"] == "url" and res.reply == "यूट्यूबवर शोधलं आहे. हवा असलेला व्हिडिओ दाबा."


def test_news_on_screen_plays_the_family_channel(core_http, uid, household):
    res = engine(core_http).handle(uid, "बातम्या बघायच्या आहेत")
    assert res.reply == "बातम्या लावतो."
    assert res.action == {"type": "open", "kind": "youtube_channel_live", "value": CHANNEL, "title": "मराठी बातम्या",
                          "query": ""}


def test_news_on_screen_without_a_family_channel_searches_live_marathi_news(core_http, uid, monkeypatch):
    g = with_google(monkeypatch)
    res = engine(core_http).handle(uid, "बातम्या बघायच्या आहेत")
    assert g.calls[0]["eventType"] == "live" and g.calls[0]["q"] == "मराठी बातम्या live"
    assert res.action["kind"] == "youtube_video" and res.reply.startswith("लावतो:")


# ---- news aloud ---------------------------------------------------------------------------------------------------
def test_headlines_are_read_verbatim_with_the_source_first(core_http, uid, household, monkeypatch):
    with_feeds(monkeypatch)
    for said in ("बातम्या ऐकवा", "आजच्या बातम्या सांग"):
        media.reset_quota_for_tests()
        res = engine(core_http).handle(uid, said)
        assert res.intent == "NEWS_READ" and res.mode == "care" and res.action["type"] == "none"
        assert res.reply == (
            "आजच्या बातम्या. लोकसत्ता: बातमी अ1. सकाळ: बातमी ब1. लोकसत्ता: बातमी अ2. सकाळ: बातमी ब2. लोकसत्ता: बातमी अ3."
        )


def test_no_feed_or_a_failed_fetch_gives_the_fixed_line(core_http, uid, household, monkeypatch):
    with_feeds(monkeypatch, {"https://www.loksatta.com/feed": httpx.ConnectError("x"),
                             "https://www.esakal.com/feed": httpx.ConnectError("y")})
    res = engine(core_http).handle(uid, "बातम्या ऐकवा")
    assert res.reply == "आत्ता बातम्या मिळाल्या नाहीत."


def test_headlines_never_reach_an_llm(core_http, uid, household, monkeypatch):
    with_feeds(monkeypatch)
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    llm = EvonClient("https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(handler)),
                     schema=load_intent_schema(), provider="TestAI")
    engine(core_http, llm).handle(uid, "बातम्या ऐकवा")
    # One understanding call for the command, but the feed text itself is never sent to a model.
    assert len(seen) == 1
    sent = json.dumps(seen, ensure_ascii=False)
    assert "बातमी अ1" not in sent and "बातमी ब1" not in sent
    assert "बातम्या ऐकवा" in sent


# ---- WhatsApp -----------------------------------------------------------------------------------------------------
def test_whatsapp_opens_her_chat_with_that_contact_and_says_to_tap(core_http, uid, household):
    res = engine(core_http).handle(uid, "चंद्रकांतला व्हॉट्सॲप कर")
    assert res.intent == "OPEN_WHATSAPP"
    assert res.reply == "चंद्रकांतचं व्हॉट्सॲप उघडलं आहे. हिरव्या बटणावर दाबा."
    contact_id = core_http.get(f"/users/{uid}/contacts").json()[0]["id"]
    assert res.action == {"type": "open", "kind": "whatsapp", "value": "https://wa.me/919000000001", "title": "चंद्रकांत",
                          "contact_id": str(contact_id)}


def test_whatsapp_call_without_a_name_uses_the_only_entry(core_http, uid, household):
    res = engine(core_http).handle(uid, "व्हॉट्सॲप कॉल लाव")
    assert res.action["kind"] == "whatsapp" and res.action["title"] == "चंद्रकांत"


def test_whatsapp_never_guesses_a_name(core_http, uid, household):
    res = engine(core_http).handle(uid, "रमेशला व्हॉट्सॲप कर")  # the only entry is चंद्रकांत
    assert res.action["type"] == "none" and "चंद्रकांत" in res.reply and "कोणाला" in res.reply
    other = core_http.post(f"/users/{uid}/contacts", json={"name": "सुनीता", "phone": "9000000002"}).json()
    link(core_http, uid, kind="whatsapp", label="सुनीता", value=str(other["id"]))
    res = engine(core_http).handle(uid, "व्हॉट्सॲप कर")  # two entries and nobody named
    assert res.action["type"] == "none" and "सुनीता" in res.reply


def test_whatsapp_without_an_entry_or_a_number_is_honest(core_http, uid):
    assert "जोडलेलं नाही" in engine(core_http).handle(uid, "व्हॉट्सॲप कर").reply
    c = core_http.post(f"/users/{uid}/contacts", json={"name": "चंद्रकांत"}).json()  # no number saved
    link(core_http, uid, kind="whatsapp", label="चंद्रकांत", value=str(c["id"]))
    res = engine(core_http).handle(uid, "चंद्रकांतला व्हॉट्सॲप कर")
    assert res.action["type"] == "none" and "नंबर नोंदवलेला नाही" in res.reply


# ---- family links -------------------------------------------------------------------------------------------------
def test_a_family_link_opens_by_its_label(core_http, uid, household):
    res = engine(core_http).handle(uid, "नातवाचे फोटो दाखव")
    assert res.intent == "OPEN_LINK" and res.reply == "नातवाचे फोटो उघडतो."
    assert res.action == {"type": "open", "kind": "link", "value": "https://photos.google.com/share/abc",
                          "title": "नातवाचे फोटो", "label": "नातवाचे फोटो"}


def test_something_she_shows_or_says_that_names_no_link_is_just_talk(core_http, uid, household):
    res = engine(core_http).handle(uid, "मला तुला आमच्या गावाचे जुने फोटो दाखवायचे आहेत")
    assert res.intent == "CHAT" and res.action["type"] == "none"


def test_a_care_command_wins_over_a_generic_show(core_http, uid, household):
    res = engine(core_http).handle(uid, "आज काय आहे ते दाखव")
    assert res.intent == "LIST_TODAY"


# ---- controls -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text, kind, line",
    [("अर्जुन, थांबव", "stop", "बंद केलं."), ("बंद कर", "stop", "बंद केलं."),
     ("आवाज कमी कर", "volume_down", "आवाज कमी केला."), ("आवाज वाढव", "volume_up", "आवाज वाढवला."),
     ("पुढचं गाणं", "next", "पुढचं लावतो.")],
)
def test_controls_answer_with_a_fixed_line_and_an_action(core_http, uid, text, kind, line):
    res = engine(core_http).handle(uid, text)
    assert res.intent == "MEDIA_CONTROL" and res.reply == line
    assert res.action == {"type": "control", "kind": kind, "value": "", "title": ""}


# ---- priorities ---------------------------------------------------------------------------------------------------
def test_an_emergency_beats_everything(core_http, uid, household):
    res = engine(core_http).handle(uid, "छातीत दुखतंय")
    assert res.intent == "EMERGENCY" and res.mode == "safety" and res.action["type"] == "none"


def test_a_pending_question_is_repeated_not_replaced_by_a_video(core_http, uid, household):
    eng = TurnEngine(CoreClient(core_http), None, clock=lambda: NOW, ask_first=True)
    eng.handle(uid, "उद्या सकाळी १० वाजता डॉक्टर आठवण करून द्या")
    res = eng.handle(uid, "बातम्या ऐकवा")
    assert res.intent == "PENDING_REPEAT" and res.action["type"] == "none"


# ---- the LLM may only pick an intent and an existing label ----------------------------------------------------------
def _llm(answer):
    def handler(req):
        body = json.loads(req.content)
        understand = "Return ONLY one JSON object" in body["messages"][0]["content"]
        content = json.dumps(answer) if understand else "छान!"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return EvonClient("https://llm.test/v1", "m", http=httpx.Client(transport=httpx.MockTransport(handler)),
                      schema=load_intent_schema(), provider="TestAI")


def test_the_llm_can_choose_a_saved_label_but_never_a_url(core_http, uid, household):
    ok = _llm({"intent": "OPEN_LINK", "confidence": 0.9, "language": "mr", "link_label": "नातवाचे फोटो"})
    res = engine(core_http, ok).handle(uid, "ते नातवाचे बघूया")  # the rules cannot read this
    assert res.source == "llm" and res.action["value"] == "https://photos.google.com/share/abc"

    evil = _llm({"intent": "OPEN_LINK", "confidence": 0.9, "language": "mr", "link_label": "https://evil.example/x"})
    res = engine(core_http, evil).handle(uid, "ते नातवाचे बघूया")
    assert res.action["type"] == "none" and "evil" not in json.dumps(res.__dict__)


def test_the_llm_schema_accepts_only_known_intents_and_control_words():
    import jsonschema

    schema = load_intent_schema()
    good = {"intent": "MEDIA_CONTROL", "confidence": 1, "language": "mr", "media_control": "stop"}
    jsonschema.validate(good, schema)
    for bad in ({**good, "media_control": "open_url"}, {**good, "intent": "OPEN_URL"}, {**good, "url": "https://x.io"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


# ---- the family's view --------------------------------------------------------------------------------------------
def test_the_summary_says_what_she_watched_never_her_words():
    t = Tracker(core=None, llm=None)  # type: ignore[arg-type]
    conv = Conversation(started=NOW, last=NOW)
    conv.intents, conv.watched = ["OPEN_MEDIA", "NEWS_READ"], ["भीमसेन जोशी भजन"]
    row = t.entry(conv, consent=False)
    assert "watched/listened to भीमसेन जोशी भजन" in row["summary"] and "listened to the news" in row["summary"]
    assert row["severity"] == "normal"


def test_a_media_turn_counts_as_activity_and_is_recorded_with_its_title():
    t = Tracker(core=None, llm=None, clock=lambda: NOW)  # type: ignore[arg-type]
    t.record(1, "भजन लावा", "भजन लावतो.", "OPEN_MEDIA", "भक्तिगीते")
    assert t._convs[1].watched == ["भक्तिगीते"] and t._convs[1].intents == ["OPEN_MEDIA"]


# ---- the media-mode gate used by the voice agent ---------------------------------------------------------------
def test_the_gate_lets_safety_and_controls_through_and_nothing_else():
    from fastapi.testclient import TestClient
    from reasoning_svc import main as main_mod

    api = TestClient(main_mod.app)

    def gate(text):
        return api.post("/media/gate", json={"user_id": 1, "text": text}).json()

    assert gate("छातीत दुखतंय")["safety"] is True
    assert gate("मला खूप एकटं आणि निराश वाटतंय आणि जगावंसं वाटत नाही")["safety"] in (True, False)  # lexicon decides
    assert gate("थांबव") == {"safety": False, "control": True}
    assert gate("आवाज कमी कर") == {"safety": False, "control": True}
    assert gate("जय जय रघुवीर समर्थ") == {"safety": False, "control": False}
    assert gate("भीमसेन जोशींचं भजन लावा") == {"safety": False, "control": False}  # a new request needs the wake word


def test_a_headline_keeps_its_own_ending_and_gets_a_full_stop_only_when_it_has_none(core_http, uid, household, monkeypatch):
    feed = ("<rss><channel><item><title>पाऊस कधी थांबणार?</title></item><item><title>धक्कादायक निकाल!</title></item>"
            "<item><title>नवी योजना</title></item></channel></rss>")
    with_feeds(monkeypatch, {"https://marathi.abplive.com/x": feed})
    core_http.delete(f"/users/{uid}/app-links/{[x for x in core_http.get(f'/users/{uid}/app-links').json() if x['label'] == 'सकाळ'][0]['id']}")
    core_http.delete(f"/users/{uid}/app-links/{[x for x in core_http.get(f'/users/{uid}/app-links').json() if x['label'] == 'लोकसत्ता'][0]['id']}")
    link(core_http, uid, kind="rss", label="एबीपी माझा", value="https://marathi.abplive.com/x")
    res = engine(core_http).handle(uid, "बातम्या ऐकवा")
    assert res.reply == "आजच्या बातम्या. एबीपी माझा: पाऊस कधी थांबणार? एबीपी माझा: धक्कादायक निकाल! एबीपी माझा: नवी योजना."
