import logging

import applog
from bridge import BridgeReply, should_speak


def test_stale_reply_is_dropped_unless_it_awaits_a_confirmation():
    plain = BridgeReply("x", "care", False, 1.0)
    asks = BridgeReply("y", "care", True, 1.0)
    assert should_speak(plain, stale=False) and should_speak(asks, stale=False)
    assert not should_speak(plain, stale=True)  # the user already said something newer
    assert should_speak(asks, stale=True)  # a proposed action must be announced, or a later "yes" is blind


def test_fallback_reply_is_dropped_when_stale_too():
    assert not should_speak(BridgeReply("sorry", "fallback", False, 1.0), stale=True)


def test_file_log_is_added_once_and_receives_records(tmp_path):
    path = tmp_path / "agent.log"
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        applog.setup_file_log(path)
        applog.setup_file_log(path)  # idempotent: no duplicate lines
        root.setLevel(logging.INFO)
        logging.getLogger("livekit.agents").info("job started %s", "AJ_test")
        for h in root.handlers:
            h.flush()
        assert path.read_text(encoding="utf-8").count("job started AJ_test") == 1
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()
