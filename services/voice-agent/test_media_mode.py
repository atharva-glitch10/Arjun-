"""Media mode: while a video plays, the mic also hears the video. Only her wake word, a bare control or a
SAFETY phrase reaches reasoning; everything else is ignored without keeping the words. All local, no network."""

import json

import httpx
from bridge import BridgeReply, ask_reasoning
from media import (
    ATTR_MEDIA,
    CONTROL_PHRASES,
    MediaState,
    is_bare_control,
    should_send,
    starts_with_wake_word,
    strip_wake_word,
)
from safety_words import DISTRESS_PHRASES, EMERGENCY_PHRASES, is_safety_phrase
from screenstate import ACTION, attributes_for
from turnlog import TurnLog

SONG = "ये जिंदगी उसी की है"


# ---- safety lexicon copy -------------------------------------------------------------------------------------
def test_the_local_safety_copy_has_the_phrases_that_matter():
    copy = " ".join(EMERGENCY_PHRASES + DISTRESS_PHRASES)
    for phrase in ("छातीत दुखतंय", "श्वास घेता येत नाही", "chest pain"):
        assert phrase in copy
    # "I have fallen" is a PATTERN in distress.py (not a phrase), and the generated copy carries the patterns too
    for text in ("मी पडले", "मी पडलो", "मला मरायचं आहे"):
        assert is_safety_phrase(text)


# ---- should_send ---------------------------------------------------------------------------------------------
def test_normal_mode_sends_everything():
    for text in ("", SONG, "आज मी बागेत गेले होते", "काहीही"):
        assert should_send(text, playing=False)


def test_playing_ignores_the_videos_own_audio():
    assert not should_send(SONG, playing=True)
    assert not should_send("आम्ही लहानपणी गावात राहायचो", playing=True)
    assert not should_send("", playing=True)


def test_playing_passes_the_wake_word_and_strips_it():
    assert should_send("अर्जुन थांबव", playing=True)
    assert strip_wake_word("अर्जुन, थांबव") == "थांबव"
    assert should_send("Arjun, volume down", playing=True)
    assert strip_wake_word("Arjun, volume down") == "volume down"


def test_playing_passes_a_bare_control_phrase():
    for phrase in ("बंद कर", "थांबव", "आवाज कमी कर", "stop", "pause", "next"):
        assert should_send(phrase, playing=True), phrase
        assert is_bare_control(phrase)
    assert not is_bare_control("बंद कर आणि मग गाणं लाव")


def test_media_controls_from_requested_short_phrases_work_without_wake_word():
    for phrase in ("बंद कर ना", "बंद करा", "थांब", "पॉज", "पुढचं", "मागचं", "आवाज वाढव", "आवाज कमी कर", "परत"):
        assert should_send(phrase, playing=True), phrase


def test_video_call_action_is_filtered_out_of_media_app_commands():
    from reasoning_svc.appcmd import parse_app_command

    assert parse_app_command("व्हिडिओ कॉल लाव") is None


def test_playing_never_ignores_a_safety_phrase():
    for phrase in ("छातीत दुखतंय", "श्वास घेता येत नाही", "मी पडले", "मला मरायचं आहे", "chest pain"):
        assert should_send(phrase, playing=True), phrase
    # a longer sentence that merely contains one is passed too: recall beats precision here
    assert should_send("अगं मला छातीत दुखतंय खूप", playing=True)


def test_playing_passes_a_long_sentence_that_starts_with_the_wake_word():
    said = "अर्जुन आज मला बागेत फिरायला जायचं आहे असं वाटतं खूप"
    assert len(said.split()) == 10 and starts_with_wake_word(said)
    assert should_send(said, playing=True)
    assert strip_wake_word(said) == "आज मला बागेत फिरायला जायचं आहे असं वाटतं खूप"


# ---- media state ---------------------------------------------------------------------------------------------
def test_state_follows_the_page_and_the_published_actions():
    m = MediaState()
    assert not m.playing


def test_play_heartbeat_keeps_media_on_and_stale_heartbeat_clears_after_30_seconds():
    now = [0.0]
    m = MediaState(clock=lambda: now[0])
    m.on_action({"type": "open", "kind": "youtube_video"})
    assert not m.playing  # an action is not proof the page/player started
    m.on_page_state("playing")
    for _ in range(6):
        now[0] += 10
        m.on_page_state("playing")
        assert not m.heartbeat_expired()
    now[0] += 30
    assert m.heartbeat_expired()
    m.on_page_state("playing")
    assert m.playing
    m.on_page_state("stopped")
    assert not m.playing
    m.on_action({"type": "open", "kind": "youtube_video", "value": "x"})
    assert not m.playing  # media gating starts only after the player confirms playback
    m.on_page_state("playing")
    assert m.playing
    m.on_action({"type": "control", "kind": "volume_down"})
    assert m.playing  # a volume change does not end the video
    m.on_action({"type": "control", "kind": "stop"})
    assert not m.playing
    m.on_action({"type": "open", "kind": "whatsapp", "value": "https://wa.me/1"})
    assert not m.playing  # a chat window has no video audio
    m.on_page_state("playing")
    m.reset()
    assert not m.playing


# ---- bridge + screen -----------------------------------------------------------------------------------------
def test_bridge_carries_the_action():
    action = {"type": "open", "kind": "youtube_video", "video_id": "AAAAAAAAAAA", "title": "भजन"}
    body = {"reply": "भजन लावतो.", "mode": "care", "awaiting_confirmation": False, "action": action}
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))
    assert ask_reasoning(1, "भजन लावा", client).action == action
    body.pop("action")
    assert ask_reasoning(1, "x", client).action is None


def test_the_action_is_published_with_the_turn_number():
    reply = BridgeReply("भजन लावतो.", "care", False, 1.0,
                        action={"type": "open", "kind": "youtube_video", "video_id": "AAAAAAAAAAA", "title": "भजन"})
    attrs = attributes_for(reply, 7)
    assert json.loads(attrs[ACTION]) == {"type": "open", "kind": "youtube_video", "video_id": "AAAAAAAAAAA",
                                         "title": "भजन", "turn": 7}
    assert attributes_for(BridgeReply("ठीक आहे", "care", False, 1.0), 8)[ACTION] == ""


# ---- the turn log --------------------------------------------------------------------------------------------
def test_turnlog_records_the_action_type_and_whether_it_was_ignored(tmp_path):
    log = TurnLog("mr-IN", tmp_path / "t.jsonl")
    idx = log.reasoning_started("हो", t=1.0)
    log.reasoning_done(idx, 2.0, "ठीक", "care", action_type="control")
    log.speaking_for(idx)
    log.agent_speaking(3.0)
    log.final_transcript(4.0, SONG, None)
    log.ignore_collected("ignored_media")
    rows = [json.loads(x) for x in (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["action_type"] == "control" and rows[0]["ignored_media"] is False
    assert rows[1]["ignored_media"] is True and rows[1]["transcript"] == ""


def test_at_least_one_control_phrase_is_short():
    assert all(len(p.split()) <= 4 for p in CONTROL_PHRASES) and ATTR_MEDIA == "arjun.media"
