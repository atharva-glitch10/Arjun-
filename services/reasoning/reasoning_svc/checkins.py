"""Reading a spoken answer to a day check-in, and spotting a topic she volunteers on her own.

Only called when core-api says the prompt really reached the elder (`heard`): a pending question, an open reminder
draft, an undo window and a recent medicine prompt all take precedence. The words here decide only "done" or
"skipped" for the topic that was asked (rules first; turn.py asks the LLM for a strict JSON reading only when the
rules cannot tell). The fixed reply templates live in replies.py. The word lists are UNVERIFIED (no native-speaker
review), like the safety lexicons.
"""

from .parser import NO, YES, has_med_word
from .textutil import has_any, normalize, tokens

# "I did it" for a meal / walk. Medicine words are excluded by the caller's has_med_word check.
DONE_WORDS = (
    "झालं", "झाले", "झाला", "झाली", "केलं", "केली", "केला", "खाल्लं", "खाल्ले", "खाल्ला", "खाल्ली", "जेवले", "जेवलो",
    "गेलो", "गेले", "गेलात", "पूर्ण", "केलंय", "झालंय", "done", "finished", "ate", "had", "went", "walked",
    "completed", "did it", "kar liya", "ho gaya", "kela", "zala", "geli", "gela", "जेवण झालं", "नाश्ता केला",
    "फिरून आले", "फिरून आलो",
)
# A clear no. Longer negative phrases are listed too, because "झालं नाही" also contains a done word.
SKIP_WORDS = (
    "नाही केलं", "नाही केली", "केलं नाही", "केली नाही", "केले नाही", "नाही झालं", "नाही झाले", "नाही झाला",
    "नाही झाली", "झालं नाही", "झाले नाही", "झाला नाही", "झाली नाही", "राहिलं", "राहिले", "सोडलं", "टाळलं",
    "जाता आलं नाही", "जेवले नाही", "जेवलो नाही", "नाही जेवले", "नाही जेवलो", "खाल्लं नाही", "खाल्ले नाही",
    "खाल्ला नाही", "नाही खाल्लं", "नाही गेले", "नाही गेलो", "नाही गेलात", "गेले नाही", "गेलो नाही",
    "गेलात नाही", "फिरले नाही", "फिरलो नाही", "नाही फिरले", "नाही फिरलो", "अजून नाही", "नहीं किया", "नहीं हुआ", "nahi kela", "nahi zala", "nahi keli",
    "skipped", "skip", "did not", "didn't", "could not", "couldn't", "not done", "no time",
)

# Topic-specific wording, checked BEFORE the general lists (these are the answers the general lists cannot see).
_TOPIC: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "sleep": (
        ("लागली", "लागला", "छान", "चांगली", "बरी", "झोपले", "झोप झाली", "slept", "slept well", "नींद आई"),
        (
            "लागली नाही", "नाही लागली", "लागलीच नाही", "झोप आली नाही", "झोप नाही", "नीट नाही", "जागी", "जागीच",
            "झोपले नाही", "didn't sleep", "couldn't sleep", "नींद नहीं", "नीट लागली नाही", "नीट झोप लागली नाही",
            "ठीक नाही", "छान नाही", "चांगली नाही", "बरी नाही", "नीट नाही लागली",
        ),
    ),
    "appt": (
        ("लक्षात आहे", "आठवतंय", "माहिती आहे", "माहीत आहे", "याद है", "remember", "i remember"),
        ("विसरले", "विसरलो", "लक्षात नाही", "आठवत नाही", "विसरले होते", "भूल गई", "भूल गया", "forgot", "dont remember"),
    ),
    "interest": (
        ("हवं", "हवे", "ऐकायचं", "ऐकायचे", "लाव", "लावा", "चालेल", "ऐकते", "ऐकतो", "play", "सुरू", "लावू"),
        ("नको", "आत्ता नको", "आज नको", "नंतर", "no"),
    ),
    "home": (
        ("बोलले", "बोललो", "बोलणं झालं", "बोलणे झाले", "फोन आला", "आला होता", "आले होते", "spoke", "talked"),
        ("नाही बोलले", "बोलले नाही", "बोललो नाही", "नाही बोललो", "बोलणं झालं नाही", "बोलणं नाही झालं", "नाही झालं", "नाही"),
    ),
}


def topic_of(kind: str) -> str:
    """'appt12' -> 'appt', 'rem3' -> 'appt' (same wording), 'water3' -> 'water', else the kind itself."""
    if kind.startswith("appt") or kind.startswith("rem"):
        return "appt"
    if kind.startswith("water"):
        return "water"
    return kind


def answer_for(kind: str, text: str) -> str | None:
    """'done' / 'skipped' when the words clearly answer THIS check-in, else None (the rules cannot tell)."""
    norm = normalize(text)
    if not norm:
        return None
    topic = topic_of(kind)
    if topic in _TOPIC:
        done, skip = _TOPIC[topic]
        if has_any(norm, skip):
            return "skipped"
        if has_any(norm, done):
            return "done"
        if len(tokens(norm)) <= 4:  # a bare "हो" / "नाही"
            if has_any(norm, NO):
                return "skipped"
            if has_any(norm, YES):
                return "done"
        return None
    return answer_from_text(text)


def answer_from_text(text: str) -> str | None:
    """'done' / 'skipped' when the words clearly answer a meal / walk prompt, else None."""
    norm = normalize(text)
    if not norm or has_med_word(norm):
        return None  # medicine talk is never a meal answer
    if has_any(norm, SKIP_WORDS):
        return "skipped"
    if has_any(norm, DONE_WORDS):
        return "done"
    toks = tokens(norm)
    if len(toks) <= 4:  # a bare "हो" / "नाही" answers "did you have breakfast?"
        if has_any(norm, NO):
            return "skipped"
        if has_any(norm, YES):
            return "done"
    return None


# ---- a topic she tells us on her own ("जेवले"): the check-in about it is then not asked ---------------------------
_MEAL_LUNCH = ("दुपारचं जेवण", "दुपारचे जेवण", "दुपारी जेवले", "दुपारी जेवलो", "lunch")
_MEAL_DINNER = ("रात्रीचं जेवण", "रात्रीचे जेवण", "रात्री जेवले", "रात्री जेवलो", "dinner")
_MEAL_PLAIN = ("जेवले", "जेवलो", "जेवण झालं", "जेवण झाले")
_WALK = ("फिरून आले", "फिरून आलो", "फिरायला गेले", "फिरायला गेलो", "walk करून आले", "walked")


def volunteered_topic(text: str, hour: int) -> tuple[str, str] | None:
    """(topic, 'done'|'skipped') when she volunteers a meal or a walk, else None.

    Only a clear statement counts. A plain "जेवले" is a lunch between 11 and 16 and a dinner from 18; any other hour
    is ambiguous and is NOT guessed (boundary 3). Questions and medicine talk never count."""
    norm = normalize(text)
    if not norm or has_med_word(norm) or "?" in text:
        return None
    negative = has_any(norm, SKIP_WORDS)
    status = "skipped" if negative else "done"
    if has_any(norm, ("नाश्ता", "नाश्ता केला", "नाश्ता झाला", "breakfast")) and (negative or has_any(norm, DONE_WORDS)):
        return "breakfast", status
    if has_any(norm, _MEAL_LUNCH) and (negative or has_any(norm, DONE_WORDS)):
        return "lunch", status
    if has_any(norm, _MEAL_DINNER) and (negative or has_any(norm, DONE_WORDS)):
        return "dinner", status
    if not negative and has_any(norm, _WALK):
        return "walk", "done"
    if has_any(norm, _MEAL_PLAIN) or (negative and "जेवण" in norm):
        if 11 <= hour < 16:
            return "lunch", status
        if 18 <= hour < 23:
            return "dinner", status
    return None
