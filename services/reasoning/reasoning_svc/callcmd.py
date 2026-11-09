"""Named-contact call requests in Marathi / Hindi / English / code-mixed speech (rules fallback, 2026-11-09).

"राहुलला कॉल कर", "राहुल को कॉल करो", "राहुल को कॉल लगाओ जरा", "फोन लाव / फोन जोड", "राहुल से बात करनी है", "मुलाला / बेटे को फोन
लगाओ", "call my son", "call Rahul". Logs of 2026-11-09 showed two such sentences falling through to CHAT, because the old
CALL_ACTION list only knew the exact pairs "कॉल कर / फोन लाव". The test here is looser on word order and endings but strict on
mood: an imperative or a wish ("करो / लगाओ / करायचाय / बात करनी है"), never a past tense, a negation or a reminder. UNVERIFIED
word lists (no native speaker, no real ASR output); the LLM schema carries the same examples and normally decides first."""

from __future__ import annotations

from .textutil import normalize, tokens

_CALL_NOUN = frozenset({"कॉल", "काल", "फोन", "फ़ोन", "फॉन", "call", "phone", "fon", "phon", "foan", "dial"})
# imperative / wish forms that make a call happen (matched as whole tokens, after normalisation)
_DO = frozenset({
    "कर", "करो", "करा", "करना", "करनी", "करें", "करिए", "करिये", "करून", "करायचा", "करायचं", "करायची", "करायचाय", "करायचंय",
    "लाव", "लावा", "लावून", "लावतो", "लगा", "लगाओ", "लगाइए", "लगाइये", "लगाना", "लगानी", "जोड", "जोडा", "जोडून", "जोड़ो", "जोड़",
    "कनेक्ट", "मिला", "मिलाओ", "मिलाइए", "kar", "karo", "kara", "karna", "karaycha", "laga", "lagao", "lagana", "lav", "lava",
    "joda", "jod", "laav", "laaw", "lawa", "lagav", "कारो", "कारा", "make", "connect", "give", "get", "ring", "dial", "place", "start",
})
# "I want to talk to X" (no call word at all)
_TALK_PHRASES = (
    "से बात करनी है", "से बात करना है", "से बात करनी", "से बात करवा", "से बात कराओ", "से बात कराइए", "बात करवाओ", "बात कराओ",
    "शी बोलायचं", "शी बोलायचंय", "शी बोलायचे", "शी बोलायचा", "शी बात करायची", "शी बोलव", "शी बोलवा", "ला बोलवा", "ला बोलव",
    "talk to", "speak to", "speak with", "talk with", "want to talk", "want to speak",
)
_EN_VERB = frozenset({"call", "phone", "ring", "dial"})
_EN_FILLER = frozenset({"please", "pls", "kindly", "can", "could", "would", "you", "just", "now", "i", "want", "to", "wanna", "need", "let", "me", "lets", "let's", "hey", "arjun"})
_NEGATION = frozenset({"नको", "नका", "मत", "नहीं", "नही", "नाही", "नये", "नए", "not", "dont", "don't", "no", "never"})
_REMIND = frozenset({"आठवण", "याद", "remind", "reminder", "रिमाइंडर", "सांग", "बता"})  # "remind me to call" is a reminder, not a call
_PAST = frozenset({"केला", "केली", "केले", "किया", "की", "आला", "आली", "आया", "आई", "called", "rang"})

_SON = ("मुलगा", "मुलाला", "मुलास", "मुलाशी", "मुलाकडे", "बेटा", "बेटे", "बेटेको", "बेटे को", "बेटे से", "son")
_DAUGHTER = ("मुलगी", "मुलीला", "मुलीशी", "बेटी", "बेटीको", "daughter")


def is_call_request(text: str) -> bool:
    """True when this sentence asks Arjun to ring someone (a named contact, a role like "my son", or "the family")."""
    norm = normalize(text)
    toks = tokens(norm)
    if not toks or any(t in _NEGATION for t in toks) or any(t in _REMIND for t in toks) or any(t in _PAST for t in toks):
        return False
    if any(p in norm for p in _TALK_PHRASES):
        return True
    if any(t in _CALL_NOUN for t in toks) and any(t in _DO for t in toks):
        return True
    # English imperative: "call Rahul", "please call my son", "phone Rahul now" (the verb IS the call word)
    if len(toks) < 2 or not all(t.isascii() for t in toks):
        return False
    rest = list(toks)
    while rest and rest[0] in _EN_FILLER:
        rest.pop(0)
    return len(rest) >= 2 and rest[0] in _EN_VERB


def role_of(text: str) -> str | None:
    """"son" / "daughter" when she names a family ROLE instead of a person ("मुलाला फोन लाव", "call my son")."""
    toks = set(tokens(normalize(text)))
    if toks & set(_SON):
        return "son"
    if toks & set(_DAUGHTER):
        return "daughter"
    return None


def relation_matches(relation: str, role: str) -> bool:
    rel = (relation or "").casefold()
    words = ("son", "मुलग", "बेटा") if role == "son" else ("daughter", "मुलगी", "बेटी")
    return any(w in rel for w in words)
