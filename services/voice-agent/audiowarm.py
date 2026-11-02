"""Initialise LiveKit's audio resampler (soxr) ONCE, on one thread, before the voice session starts.

livekit_ffi.dll (Windows) aborts with "Assertion failed! ... soxr-sys/src/fft4g_cache.h line 13,
LSX_FFT_BR == NULL": soxr's process-wide FFT cache is not thread-safe on FIRST initialisation, and the session
starts two resamplers at once (mic 48k -> STT 16k, TTS 16k -> output 24k). One tiny resample per process first
sets the cache up; later users go through soxr's reader/writer lock, which is thread-safe.
"""

import logging

log = logging.getLogger("arjun.audiowarm")

_WARMED = False


def warm_audio_resampler() -> bool:
    """Idempotent. True when warmed (or already warm); False if LiveKit is not installed."""
    global _WARMED
    if _WARMED:
        return True
    try:
        from livekit import rtc
    except ImportError:
        return False
    for src, dst in ((48000, 16000), (16000, 24000)):  # the two pairs the session uses
        n = src // 100  # 10 ms of silence
        r = rtc.AudioResampler(src, dst, num_channels=1)
        r.push(rtc.AudioFrame(data=b"\x00\x00" * n, sample_rate=src, num_channels=1, samples_per_channel=n))
        r.flush()
    _WARMED = True
    log.info("audio resampler warmed (soxr FFT cache initialised on one thread)")
    return True
