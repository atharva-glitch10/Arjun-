from reasoning_svc.textutil import marathi_evidence
from reasoning_svc.turn import _reply_language


def test_marathi_words_beat_hindi_label():
    assert _reply_language("hi-IN", "माझ्या छातीत दुखतंय", "mr") == "mr"
    assert _reply_language("hi-IN", "छातीत दुखतंय.", "mr") == "mr"


def test_hindi_stays_hindi():
    assert marathi_evidence("मेरे सीने में दर्द हो रहा है") == 0
    assert _reply_language("hi-IN", "मेरे सीने में दर्द हो रहा है", "mr") == "hi"
    assert _reply_language("hi-IN", "मुझे दवाई के बारे में बताओ", "mr") == "hi"
    assert _reply_language("en-IN", "remind me tomorrow", "mr") == "en"


def test_hindi_emergency_words_not_marathi():
    for t in ("खून बह रहा है", "सांस नहीं आ रही", "मैं गिर गया", "सीने में दर्द है"):
        assert marathi_evidence(t) == 0, t
