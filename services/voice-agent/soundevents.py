"""Opt-in, in-memory sound event detection. Audio frames are never written to disk or logs."""

from __future__ import annotations

import csv
import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from livekit import rtc
from livekit.agents.voice.io import AudioInput

log = logging.getLogger("arjun.soundevents")
WINDOW_SAMPLES = 15_360  # YAMNet's 0.96 s window at 16 kHz.
TARGET_RATE = 16_000
THRESHOLDS = {"cough": 0.70, "scream": 0.75, "crying": 0.70, "bang": 0.78}
LABELS = {
    "cough": ("cough",),
    "scream": ("screaming", "shout", "bellow", "yell", "whoop"),
    "crying": ("crying, sobbing", "whimper", "wail, moan"),
    "bang": ("bang", "glass", "shatter", "smash, crash", "thump, thud", "boom"),
}


@dataclass(frozen=True)
class SoundEvent:
    label: str
    confidence: float
    check_in: bool = False


class SoundCheckWindow:
    """One fixed 20-second answer window for a scream/bang safety check-in."""

    def __init__(self, timeout_s: float = 20.0) -> None:
        self.timeout_s = timeout_s
        self.deadline: float | None = None

    def start(self, now: float) -> None:
        self.deadline = now + self.timeout_s

    def answered(self) -> None:
        self.deadline = None

    def should_escalate(self, now: float) -> bool:
        if self.deadline is None or now < self.deadline:
            return False
        self.deadline = None
        return True


class Classifier(Protocol):
    def classify(self, waveform: np.ndarray) -> dict[str, float]: ...


def enabled(env: dict[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return values.get("ARJUN_SOUND_EVENTS", "0").strip().lower() in {"1", "true", "yes", "on"}


def classify_scores(scores: dict[str, float]) -> list[SoundEvent]:
    """Map YAMNet class scores to the few event labels we retain, applying conservative thresholds."""
    detected: list[SoundEvent] = []
    folded = {name.casefold(): float(score) for name, score in scores.items()}
    for label, aliases in LABELS.items():
        confidence = max((folded.get(alias, 0.0) for alias in aliases), default=0.0)
        if confidence >= THRESHOLDS[label]:
            detected.append(SoundEvent(label, min(1.0, max(0.0, confidence))))
    return detected


class OnnxYamnet:
    """CPU-only ONNX Runtime adapter for a user-supplied YAMNet ONNX file + class map CSV."""

    def __init__(self, model_path: str | Path, labels_path: str | Path | None = None) -> None:
        import onnxruntime as ort

        model = Path(model_path)
        labels = Path(labels_path) if labels_path else model.with_name("yamnet_class_map.csv")
        if not model.is_file() or not labels.is_file():
            raise FileNotFoundError("YAMNet ONNX model or class map is missing")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.names: list[str] = []
        with labels.open(encoding="utf-8", newline="") as source:
            self.names = [row["display_name"] for row in csv.DictReader(source)]
        self.output_name = self.session.get_outputs()[0].name

    def classify(self, waveform: np.ndarray) -> dict[str, float]:
        scores = self.session.run([self.output_name], {self.input_name: waveform.astype(np.float32, copy=False)})[0]
        mean_scores = np.asarray(scores).mean(axis=0)
        wanted = {name.casefold() for names in LABELS.values() for name in names}
        return {name: float(mean_scores[i]) for i, name in enumerate(self.names) if name.casefold() in wanted}


class SoundEventMonitor:
    """Bounded queue + one daemon worker. The worker keeps only transient audio windows in RAM."""

    def __init__(self, classifier: Classifier, callback: Callable[[SoundEvent], None]) -> None:
        self.classifier = classifier
        self.callback = callback
        self.frames: queue.Queue[tuple[np.ndarray, int, int]] = queue.Queue(maxsize=24)
        self.running = True
        self._last_event: dict[str, float] = {}
        self._danger: tuple[str, float] | None = None
        self._cpu_credit = 0.096
        self._cpu_updated = time.monotonic()
        self.worker = threading.Thread(target=self._run, name="arjun-sound-events", daemon=True)
        self.worker.start()

    def submit(self, frame: rtc.AudioFrame) -> None:
        """Copy one frame into a bounded queue; drop on overload and never block LiveKit audio."""
        try:
            raw = np.frombuffer(frame.data, dtype=np.int16).copy()
            self.frames.put_nowait((raw, frame.sample_rate, frame.num_channels))
        except (queue.Full, ValueError):
            return

    def close(self) -> None:
        self.running = False
        if threading.current_thread() is not self.worker:
            self.worker.join(timeout=1.0)

    def _run(self) -> None:
        pending = np.empty(0, dtype=np.float32)
        source_rate: int | None = None
        while self.running:
            try:
                data, rate, channels = self.frames.get(timeout=0.2)
            except queue.Empty:
                continue
            if source_rate != rate:
                pending = np.empty(0, dtype=np.float32)
                source_rate = rate
            mono = data.astype(np.float32) / 32768.0
            if channels > 1:
                mono = mono.reshape(-1, channels).mean(axis=1)
            if rate != TARGET_RATE:
                count = max(1, round(len(mono) * TARGET_RATE / rate))
                mono = np.interp(np.linspace(0, len(mono) - 1, count), np.arange(len(mono)), mono).astype(np.float32)
            pending = np.concatenate((pending, mono))
            if len(pending) < WINDOW_SAMPLES:
                continue
            window, pending = pending[:WINDOW_SAMPLES], pending[WINDOW_SAMPLES:]
            self._process(window)

    def _process(self, window: np.ndarray) -> None:
        rms = float(np.sqrt(np.mean(np.square(window))))
        now = time.monotonic()
        self._cpu_credit = min(0.096, self._cpu_credit + (now - self._cpu_updated) * 0.10)
        self._cpu_updated = now
        if self._cpu_credit < 0.001:
            return
        started = time.thread_time()
        try:
            scores = self.classifier.classify(window)
        except Exception as exc:  # classifier problems must not stop speech recognition
            log.warning("sound classifier unavailable (%s)", type(exc).__name__)
            self.close()
            return
        spent = time.thread_time() - started
        self._cpu_credit -= spent
        events = classify_scores(scores)
        active = max(events, key=lambda event: event.confidence, default=None)

        if self._danger is not None:
            danger_label, danger_conf = self._danger
            self._danger = None
            if rms < 0.012:
                self.callback(SoundEvent(danger_label, danger_conf, check_in=True))
        if active is None:
            return
        if now - self._last_event.get(active.label, 0.0) < 60.0:
            return
        self._last_event[active.label] = now
        if active.label in {"scream", "bang"}:
            self._danger = (active.label, active.confidence)
        self.callback(active)


class SoundEventAudioInput(AudioInput):
    """Transparent tee: forwards original frames to LiveKit and a transient copy to the classifier."""

    def __init__(self, source: AudioInput, monitor: SoundEventMonitor) -> None:
        super().__init__(label="SoundEventAudioInput", source=source)
        self.monitor = monitor

    async def __anext__(self) -> rtc.AudioFrame:
        frame = await super().__anext__()
        self.monitor.submit(frame)
        return frame
