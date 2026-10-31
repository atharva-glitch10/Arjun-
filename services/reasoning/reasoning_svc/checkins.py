"""Reading a spoken meal / walk check-in answer.

Only called when core-api says the prompt really reached the elder (`heard`): a pending question,
an open reminder draft, an undo window and a recent medicine prompt all take precedence. The words
here decide only "done" or "skipped"; the fixed reply templates live in replies.py.
"""

from .parser import NO, YES, has_med_word
from .textutil import has_any, normalize, tokens

# "I did it" for a meal / walk. Medicine words are excluded by the caller's has_med_word check.
DONE_WORDS = (
    "झालं", "झाले", "झाला", "केलं", "केली", "केला", "खाल्लं", "खाल्ले", "गेलो", "गेले", "गेलात",
    "पूर्ण", "केलंय", "झालंय", "done", "finished", "ate", "had", "went", "walked", "completed",
    "did it", "kar liya", "ho gaya", "kela", "zala", "geli", "gela",
)
# A clear no. Longer negative phrases are listed too, because "झालं नाही" also contains a done word.
SKIP_WORDS = (
    "नाही केलं", "नाही केली", "केलं नाही", "केली नाही", "केले नाही", "नाही झालं", "नाही झाले",
    "झालं नाही", "झाले नाही", "राहिलं", "राहिले", "सोडलं", "टाळलं", "जाता आलं नाही",
    "नहीं किया", "नहीं हुआ", "nahi kela", "nahi zala", "nahi keli", "skipped", "skip",
    "did not", "didn't", "could not", "couldn't", "not done", "no time",
)


def answer_from_text(text: str) -> str | None:
    """'done' / 'skipped' when the words clearly answer a check-in prompt, else None."""
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
