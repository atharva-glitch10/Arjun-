import threading

import audiowarm
import pytest


def test_warm_is_idempotent(monkeypatch):
    pytest.importorskip("livekit.rtc")
    monkeypatch.setattr(audiowarm, "_WARMED", False)
    assert audiowarm.warm_audio_resampler() is True
    assert audiowarm.warm_audio_resampler() is True


def test_after_warming_resamplers_in_parallel_threads_work():
    rtc = pytest.importorskip("livekit.rtc")
    audiowarm.warm_audio_resampler()
    errors = []

    def go(src, dst):
        try:
            r = rtc.AudioResampler(src, dst, num_channels=1)
            for _ in range(20):
                r.push(rtc.AudioFrame(data=b"\x00\x00" * (src // 100), sample_rate=src, num_channels=1,
                                      samples_per_channel=src // 100))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=go, args=p) for p in [(48000, 16000), (16000, 24000)] * 4]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
