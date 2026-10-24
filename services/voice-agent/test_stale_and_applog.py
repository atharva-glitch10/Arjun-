import logging

import applog
from bridge import BridgeReply, should_speak


def _r(mode="care", ask=False):
    return BridgeReply("x", mode, ask, 1.0)


def test_only_plain_care_and_companion_replies_may_be_skipped_as_stale():
    for mode in ("care", "companion", "fallback"):
        assert should_speak(_r(mode), stale=False)
        assert not should_speak(_r(mode), stale=True)  # the user already said something newer


def test_safety_replies_are_always_spoken_even_when_stale():
    # emergency / distress: 112, call out for someone, Elderline. Never dropped (CLAUDE.md boundary 8).
    assert should_speak(_r("safety"), stale=True) and should_speak(_r("safety"), stale=False)


def test_a_reply_that_asks_for_confirmation_is_always_spoken_even_when_stale():
    """Chosen over "skip it and reject the pending action": the user's request is kept, and the spoken
    question tells them what a later "हो" would execute. Together with reasoning's invariant (every
    pending action comes with awaiting_confirmation), a "हो" can never confirm an unheard action."""
    for mode in ("care", "companion"):
        assert should_speak(_r(mode, ask=True), stale=True)


def test_a_stale_confirmation_is_never_skipped_so_no_unheard_pending_action_exists():
    # Simulate the agent loop: a reply is skipped only when should_speak says no.
    replies = [_r("care", ask=True), _r("companion"), _r("safety"), _r("care")]
    skipped = [r for r in replies if not should_speak(r, stale=True)]
    assert all(not r.awaiting_confirmation and r.mode != "safety" for r in skipped)
    assert len(skipped) == 2


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


def test_structured_fields_are_written_too(tmp_path):
    path = tmp_path / "agent.log"
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        applog.setup_file_log(path)
        root.setLevel(logging.INFO)
        logging.getLogger("livekit.agents").info("registered worker", extra={"agent_name": "arjun", "id": "AW_x"})
        for h in root.handlers:
            h.flush()
        text = path.read_text(encoding="utf-8")
        assert '"agent_name": "arjun"' in text and '"id": "AW_x"' in text
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()
