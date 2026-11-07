import asyncio
import builtins
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from soundevents import (
    AudioInput,
    SoundCheckWindow,
    SoundEventAudioInput,
    SoundEventMonitor,
    classify_scores,
    enabled,
)


def test_event_thresholds_only_accept_high_confidence_labels():
    assert classify_scores({"Cough": 0.69}) == []
    assert classify_scores({"Cough": 0.70})[0].label == "cough"
    assert classify_scores({"Crying, sobbing": 0.71})[0].label == "crying"
    assert classify_scores({"Screaming": 0.76})[0].label == "scream"
    assert classify_scores({"Glass": 0.78})[0].label == "bang"


def test_feature_flag_defaults_off_and_can_be_enabled_explicitly():
    assert not enabled({})
    assert enabled({"ARJUN_SOUND_EVENTS": "1"})


def test_scream_or_bang_followed_by_silence_requests_checkin():
    class MockClassifier:
        next_scores = {"Screaming": 0.9}

        def classify(self, waveform):
            assert waveform.shape == (15_360,)
            return self.next_scores

    classifier = MockClassifier()
    events = []
    monitor = SoundEventMonitor(classifier, events.append)
    try:
        monitor._process(np.full(15_360, 0.1, dtype=np.float32))
        classifier.next_scores = {}
        monitor._process(np.zeros(15_360, dtype=np.float32))
    finally:
        monitor.close()
    assert events[0].label == "scream" and not events[0].check_in
    assert events[1].label == "scream" and events[1].check_in


def test_no_answer_at_20_seconds_escalates_but_answer_cancels():
    unanswered = SoundCheckWindow(timeout_s=20)
    unanswered.start(100)
    assert not unanswered.should_escalate(119.9)
    assert unanswered.should_escalate(120)
    assert not unanswered.should_escalate(121)

    answered = SoundCheckWindow(timeout_s=20)
    answered.start(100)
    answered.answered()
    assert not answered.should_escalate(130)


def test_audio_frames_are_transient_and_events_expose_only_label_and_confidence(tmp_path, monkeypatch):
    class MockClassifier:
        def classify(self, waveform):
            return {"Cough": 0.8}

    events = []
    monitor = SoundEventMonitor(MockClassifier(), events.append)
    def reject_file_write(*args, **kwargs):
        raise AssertionError("audio persistence is forbidden")

    monkeypatch.setattr(builtins, "open", reject_file_write)
    monkeypatch.setattr(Path, "open", reject_file_write)
    try:
        monitor._process(np.ones(15_360, dtype=np.float32))
    finally:
        monitor.close()
    assert events[0].__dict__ == {"label": "cough", "confidence": 0.8, "check_in": False}
    assert list(tmp_path.iterdir()) == []


def test_audio_tee_returns_the_original_frame_and_forwards_a_transient_copy():
    class Source(AudioInput):
        def __init__(self, frame):
            super().__init__(label="fake")
            self.frame = frame

        async def __anext__(self):
            return self.frame

    class Monitor:
        seen = None

        def submit(self, frame):
            self.seen = frame

    frame = SimpleNamespace(data=np.zeros(480, dtype=np.int16).tobytes(), sample_rate=48_000, num_channels=1)
    monitor = Monitor()
    tee = SoundEventAudioInput(Source(frame), monitor)
    returned = asyncio.run(tee.__anext__())
    assert returned is frame and monitor.seen is frame
