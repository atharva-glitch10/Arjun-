"""Marathi commands with Latin loanwords keep Marathi stock replies despite a hi-IN STT label."""

import json

import pytest
from reasoning_svc.app_replies import A
from reasoning_svc.langid import classify


@pytest.mark.parametrize("text", [
    "यूट्यूब दाखवा",
    "YouTube दाखवा",
    "video लावा",
    "व्हिडिओ लावा",
    "मला YouTube video दाखवा",
    "मग YouTube video लावा ना",
])
def test_untitled_video_asks_in_marathi(auto, uid, text, caplog):
    with caplog.at_level("INFO", logger="reasoning.turn"):
        result = auto.handle(uid, text, language_code="hi-IN")
    assert result.language == "mr"
    assert result.reply == "कोणता व्हिडिओ लावू?" == A["mr"]["ask_video"]
    assert result.intent == "OPEN_MEDIA"
    logs = [json.loads(row.message) for row in caplog.records if row.message.startswith('{"user_lang"')]
    assert logs[-1]["final_lang"] == "mr" and logs[-1]["fallback"] == "ask_video"


def test_loanwords_never_outvote_devanagari_markers():
    for text in ("मला recipe दाखवा", "माझी YouTube video दाखवा", "मग YouTube video लावा ना"):
        assert classify(text, default="hi").lang == "mr"


def test_an_english_prisma_label_cannot_make_devanagari_english():
    from reasoning_svc.turn import _reply_language

    assert _reply_language("en-IN", "आज YouTube", "mr") == "mr"


def test_marathi_stock_lines_are_distinct_from_hindi():
    from reasoning_svc import relevance
    from reasoning_svc.turn import _VARIED

    assert _VARIED["mr"][0] != _VARIED["hi"][0]
    assert A["mr"]["play_none"] != A["hi"]["play_none"]
    assert relevance.listening("मला आज बागेत फिरायला जायचं आहे", "mr").endswith("ऐकतोय, पुढे सांगा.")
