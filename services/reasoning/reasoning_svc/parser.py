"""Rule-based fallback parser: intent + slot extraction for care mode (Marathi / Hindi / English).

Used when EVON_BASE_URL is unset or Evon output fails schema validation twice.
Never guesses: ambiguous AM/PM or meal-relative times are flagged for a clarifying question.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .appcmd import parse_app_command
from .textutil import has_any, normalize, tokens

# ---- intent keywords (roman + Devanagari) -----------------------------------------------------
YES = ("ho", "hoy", "hoi", "होय", "हो", "हां", "हाँ", "haan", "han", "ha", "yes", "yeah", "ok",
       "okay", "theek", "thik", "ठीक", "बरं", "बरोबर", "kara", "कर", "kar do", "thik aahe",
       "ठीक आहे", "ठीक है", "sahi", "सही", "ji", "जी")
NO = ("nahi", "नाही", "nako", "नको", "no", "nahin", "नहीं", "mat", "नही", "nope")
DECLINE = ("aaj nahi", "आज नाही", "आज नको", "aaj nako", "ata nako", "आता नको", "not today",
           "baad mein", "बाद में", "aaj nahin", "आज नहीं")
FORGET = ("he visar", "हे विसर", "visar", "विसर", "forget this", "forget it", "bhool ja",
          "bhul ja", "भूल जा", "ye bhool jao", "delete this", "he pusun tak", "हे पुसून टाक")
SHARE_VERB = ("sang", "सांग", "dakhav", "दाखव", "share", "batao", "बताओ", "pathav", "पाठव",
              "dikhao", "दिखाओ", "bhej", "भेज")
FAMILY = ("family", "kutumb", "kutumbala", "कुटुंब", "कुटुंबाला", "mulanna", "मुलांना", "parivar",
          "परिवार", "ghari", "घरी", "gharchyana", "घरच्यांना", "ghar", "घर")
CAREGIVER = ("caregiver", "madat", "मदत", "madad", "मदद", "help", "sahayak", "सहाय्यक",
             "kalji", "काळजीवाहक", "dekhbhal", "देखभाल")
CALL = ("phone", "fone", "fon", "फोन", "call", "कॉल", "bolaycha", "बोलायचं", "bolna", "बोलना",
        "phon")
FAMILY_REL = FAMILY + ("mulga", "मुलगा", "mulgi", "मुलगी", "mulala", "मुलाला", "mulila", "मुलीला",
                       "beta", "बेटा", "beti", "बेटी", "nat", "नात", "natu", "नातू", "son",
                       "daughter", "bhau", "भाऊ", "bahin", "बहीण", "sun", "सून", "jawai", "जावई")
REMIND = ("remind", "reminder", "athvan", "आठवण", "athavan", "yaad", "याद", "yaad dilao",
          "याद दिलाओ", "remind kar", "athvan thev", "आठवण ठेव", "रिमाइंडर", "रिमाइंड")
LIST_TODAY = ("aaj kay", "आज काय", "aaj ke", "आज के", "today", "aajche", "आजचे", "aajcha",
              "आजचा", "aaj cha", "kay kay aahe", "क्या क्या है", "mazhe reminders",
              "माझे रिमाइंडर", "my reminders", "reminders", "list",
              # another day: the parser reads which day from the date word (see _list_day)
              "उद्या काय", "udya kay", "कल क्या", "kal kya", "उद्याचे", "udyache", "उद्याचा",
              "udyacha", "उद्याच्या", "परवा काय", "parva kay", "कल के", "kal ke",
              "what is tomorrow", "what's tomorrow")
APPOINTMENT = ("appointment", "apointment", "अपॉइंटमेंट", "bhet", "भेट", "doctor", "डॉक्टर",
               "dr", "clinic", "दवाखाना", "dawakhana")
QUESTION = ("kadhi", "कधी", "kevha", "केव्हा", "kab", "कब", "when", "kontya", "कोणत्या", "kitila",
            "next", "pudhchi", "पुढची", "agli", "अगली")
DONE = ("zala", "zale", "झालं", "झाले", "झाला", "keli", "kela", "केलं", "केली", "ghetli",
        "ghetla", "घेतली", "घेतला", "ho gaya", "हो गया", "kar liya", "done", "taken", "finished",
        "complete", "completed", "le li", "ले ली")

GREET = ("हॅलो", "हेलो", "हैलो", "हलो", "हॅलॉ", "hello", "hallo", "hullo", "hi", "hey", "namaste",
         "नमस्ते", "नमस्कार", "namaskar", "namaskaar", "pranam", "प्रणाम", "राम राम", "ram ram")
# "can you hear me": Marathi / Hindi / English, roman and Devanagari
_HEARING = re.compile(
    r"ऐक[ूु]\s*येत|aik[uo]+\s*yet|ऐकतोस|ऐकतोयस|aikatos|aikatoyas|सुनाई\s*(?:दे|पड़)|sunai\s*(?:de|pad)|"
    r"(?:सुन|sun)\s*(?:रहे|सकते|raha|rahe)|can you hear|hear me"
)
# a pending action a long "no" may cancel; SAVE_STORY and medicine actions are excluded on purpose
CORRECTABLE = ("CREATE_REMINDER", "COMPLETE_REMINDER", "REQUEST_CAREGIVER", "SHARE_STORY")

# ---- medicine (read-only vocabulary: the elder can report intake, never create/edit medicines) --
MED_WORDS = ("goli", "golya", "gooli", "गोळी", "गोळ्या", "dawa", "dawai", "dava", "दवा", "दवाई",
             "medicine", "medicines", "medication", "tablet", "tablets", "pill", "pills",
             "capsule", "capsules", "टॅबलेट", "tablets")
MED_STEMS = ("औषध", "aushad", "ausadh")  # औषध, औषधाची, औषधं, aushadh, ...
# questions Arjun must never answer (skip / double / late / purpose / side effect / missed dose)
MED_Q = ("skip", "double", "extra", "twice", "two", "दोन", "don", "dona", "jast", "जास्त", "jyada",
         "ज्यादा", "side", "effect", "effects", "इफेक्ट", "साइड", "why", "kashasathi", "कशासाठी",
         "kyun", "क्यों", "kiti", "किती", "kitni", "कितनी", "kitna", "कितना", "how", "visarle",
         "विसरले", "visarlo", "विसरलो", "visarli", "विसरली", "bhool", "भूल", "bhul", "भुल",
         "miss", "missed", "chukli", "चुकली", "late", "ushir", "उशीर", "der", "देर", "nako",
         "नको", "band", "बंद", "stop", "kami", "कमी", "reduce", "increase", "vadhav", "वाढव",
         "safe", "harmful", "allergy", "nahi", "नाही", "nahin", "नहीं", "not", "didn't",
         "ghetli nahi", "घेतली नाही", "ghetle nahi", "घेतले नाही", "ho gaya nahi")
MED_TAKEN_WORDS = ("ghetli", "ghetla", "ghetle", "घेतली", "घेतला", "घेतले", "le li", "ले ली",
                   "kha li", "खा ली", "taken", "took", "liya", "लिया", "li", "ली")
SNOOZE_WORDS = ("nantar", "नंतर", "baad mein", "बाद में", "later", "thodi der", "थोड़ी देर",
                "thodya velane", "थोड्या वेळाने", "pudhe", "पुढे")
MINUTE_WORDS = ("minitanni", "मिनिटांनी", "minute", "minutes", "minit", "मिनिट", "मिनट",
                "मिनिटाने")


# ---- time / day guidance -------------------------------------------------------------------
TIME_Q = ("kiti vajle", "किती वाजले", "kiti vajlet", "किती वाजलेत", "vel kay", "वेळ काय",
          "vel kiti", "वेळ किती", "kitne baje", "कितने बजे", "time kya", "time kay", "what time",
          "samay kya", "समय क्या", "time kitna", "ghadyalat kiti", "kya time hua", "time zala")
DATE_Q = ("konta divas", "कोणता दिवस", "kon ta divas", "tarikh", "तारीख", "kaun sa din",
          "कौन सा दिन", "what day", "what date", "todays date", "today's date", "aaj kya din",
          "aaj konta")
NEXT_Q = ("pudhe kay", "पुढे काय", "pudhcha kay", "next kay", "ata kay karaycha", "आता काय करायचं",
          "ata kay karu", "आता काय करू", "ab kya karna", "अब क्या करना", "what next",
          "what's next", "whats next", "what should i do", "kya karun", "kay karu", "ata kay")


# every word of these, said alone, is a yes / a no (used only while an action is pending)
_YES_TOKENS = frozenset(w for phrase in YES for w in phrase.split()) | {"चालेल", "ठेव", "ठेवा", "करा", "होऊ", "द्या"}
_NO_TOKENS = frozenset(w for phrase in NO for w in phrase.split())


def has_med_word(norm: str) -> bool:
    toks = tokens(norm)
    if has_any(norm, MED_WORDS):
        return True
    return any(t.startswith(MED_STEMS) for t in toks)


# words dropped when deriving the reminder task text
STOP = set(
    "remind reminder me kar kara karo karna dya de dena please athvan आठवण याद thev ठेव la ला ne "
    "ka का cha चा che चे chi ची aahe आहे ahe hai है hain mala मला mujhe मुझे mazya माझ्या to ko "
    "ki की ke के sang सांग bol बोल tumhi तुम्ही aaj आज udya उद्या kal कल parva परवा today tomorrow "
    "vajta वाजता baje बजे o'clock am pm at on for the a an and sakali सकाळी subah सुबह dupari "
    "दुपारी dopahar दोपहर sandhyakali संध्याकाळी shaam शाम ratri रात्री raat रात night evening "
    "morning afternoon nantar नंतर baad बाद jevna जेवणा jevan जेवण jevnanantar remind-kar "
    "रिमाइंडर रिमाइंड जेवणानंतर आपल्याला करून द्या".split()  # last three: "(मला) ... आठवण करून द्या"
)
# unambiguous time words ("साडे", "दीड", ...) never belong in a task; plain hour words are rewritten
# to digits only when they are a clock time, so "दहा मिनिटं चालणे" keeps its "दहा".
STOP |= {unicodedata.normalize("NFC", w) for w in (
    "साडे साढ़े साढे saade sade saadhe sadhe सव्वा सवा savva sawa sava पावणे पौने पाऊण pavne paune "
    "दीड डेढ़ डेढ deed dhed अडीच ढाई adeech dhai".split()
)}

PERIOD_AM = ("sakali", "sakal", "सकाळी", "सकाळ", "subah", "सुबह", "morning", "am", "a m")
PERIOD_PM = ("dupari", "दुपारी", "dopahar", "दोपहर", "afternoon", "sandhyakali", "संध्याकाळी",
             "sandhya", "shaam", "शाम", "evening", "pm", "p m")
PERIOD_NIGHT = ("ratri", "रात्री", "raat", "रात", "night")
LUNCH_WORDS = ("dupari", "दुपारी", "दुपारच्या", "duparchya", "dopahar", "दोपहर", "lunch",
               "afternoon")
DINNER_WORDS = ("ratri", "रात्री", "रात्रीच्या", "ratrichya", "raat", "रात", "dinner", "night")
MEAL_AFTER = ("jevna nantar", "जेवणानंतर", "जेवणा नंतर", "jevnanantar", "after lunch",
              "after dinner", "after meal", "after food", "khana khane ke baad", "खाने के बाद",
              "jevan zalyavar", "जेवण झाल्यावर", "jevanantar")

DATE_WORDS: dict[str, int] = {
    "aaj": 0, "आज": 0, "today": 0, "udya": 1, "उद्या": 1, "kal": 1, "कल": 1, "tomorrow": 1,
    "parva": 2, "परवा": 2, "parso": 2, "परसों": 2,
}
# ---- spoken hours: "दहा वाजता" -> "10 वाजता" before the digit regexes run ------------------------
_HOUR_WORDS = {
    "एक": 1, "ek": 1, "दोन": 2, "don": 2, "दो": 2, "do": 2, "तीन": 3, "teen": 3, "चार": 4, "char": 4,
    "पाच": 5, "paach": 5, "pach": 5, "पाँच": 5, "पांच": 5, "paanch": 5, "सहा": 6, "saha": 6,
    "छह": 6, "छः": 6, "chhe": 6, "chhah": 6, "सात": 7, "saat": 7, "आठ": 8, "aath": 8, "नऊ": 9,
    "nau": 9, "नौ": 9, "नव": 9, "nav": 9, "दहा": 10, "daha": 10, "दस": 10, "das": 10, "अकरा": 11,
    "akra": 11, "akara": 11, "ग्यारह": 11, "gyarah": 11, "बारा": 12, "bara": 12, "बारह": 12, "barah": 12,
}
# fraction prefix -> (minutes, hour offset): "साडे दहा" 10:30, "सव्वा दहा" 10:15, "पावणे दहा" 9:45
_FRACTION = {
    "साडे": (30, 0), "साढ़े": (30, 0), "साढे": (30, 0), "saade": (30, 0), "sade": (30, 0),
    "saadhe": (30, 0), "sadhe": (30, 0), "सव्वा": (15, 0), "सवा": (15, 0), "savva": (15, 0),
    "sawa": (15, 0), "sava": (15, 0), "पावणे": (45, -1), "पौने": (45, -1), "पाऊण": (45, -1),
    "pavne": (45, -1), "paune": (45, -1),
}
# single words that already mean a clock time: "दीड वाजता" 1:30, "अडीच वाजता" 2:30
_HALF_WORDS = {
    "दीड": (1, 30), "डेढ़": (1, 30), "डेढ": (1, 30), "deed": (1, 30), "dhed": (1, 30),
    "अडीच": (2, 30), "ढाई": (2, 30), "adeech": (2, 30), "dhai": (2, 30),
}


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)  # "साढ़े" may arrive precomposed or with a nukta


_HOUR_WORDS = {_nfc(k): v for k, v in _HOUR_WORDS.items()}
_FRACTION = {_nfc(k): v for k, v in _FRACTION.items()}
_HALF_WORDS = {_nfc(k): v for k, v in _HALF_WORDS.items()}


def _alt(words) -> str:  # type: ignore[no-untyped-def]
    return "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True))


_CLOCK_WORDS = r"(?:vajta|vaje|vajle|वाजता|वाजले|baje|बजे|o'clock)"
_TERM = (
    rf"(?:(?P<frac>{_alt(_FRACTION)})\s*(?P<n1>{_alt(_HOUR_WORDS)})"
    rf"|(?P<half>{_alt(_HALF_WORDS)})|(?P<n2>{_alt(_HOUR_WORDS)}))"
)
_WORD_BEFORE_CLOCK = re.compile(rf"(?<!\S){_TERM}(?=\s+{_CLOCK_WORDS}(?!\S))")
_DAYPART_WORD_HOUR = re.compile(
    r"(?<!\S)(?P<period>sakali|sakal|सकाळी|सकाळ|subah|सुबह|morning|dupari|दुपारी|dopahar|दोपहर|"
    r"afternoon|sandhyakali|संध्याकाळी|shaam|शाम|evening|ratri|रात्री|raat|रात|night)\s+"
    rf"{_TERM}(?!\S)(?!\s+(?:मिनिट|minit|minute|मिनट))"
)
_CLOCK_WORD = re.compile(rf"(?<!\S){_CLOCK_WORDS}(?!\S)")


def _clock_text(m: re.Match[str]) -> str:
    if m["half"]:
        hour, minute = _HALF_WORDS[m["half"]]
    else:
        hour = _HOUR_WORDS[m["n1"] or m["n2"]]
        minute = 0
        if m["frac"]:
            minute, delta = _FRACTION[m["frac"]]
            hour = (hour + delta) or 12
    return f"{hour}:{minute:02d}" if minute else str(hour)


def hour_words_to_digits(norm: str) -> str:
    """Rewrite a spoken clock hour as digits, only where it is clearly a time (never a bare number).

    An hour word counts when a clock word follows it ("दहा वाजता") or a day-part precedes it
    ("सकाळी दहा"). "दहा मिनिटं" stays as it is.
    """
    norm = _nfc(norm)
    norm = _WORD_BEFORE_CLOCK.sub(_clock_text, norm)
    return _DAYPART_WORD_HOUR.sub(lambda m: f"{m['period']} {_clock_text(m)}", norm)


_HOUR_MARK = re.compile(
    r"(?<!\S)(\d{1,2})(?::(\d{2}))?\s*"
    r"(?:vajta|vaje|vajle|वाजता|वाजले|baje|बजे|o'clock|am|pm|a m|p m)(?!\S)"
)
_HHMM = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_PERIOD_NUM = re.compile(
    r"(?<!\S)(?:sakali|सकाळी|subah|सुबह|dupari|दुपारी|dopahar|दोपहर|sandhyakali|संध्याकाळी|"
    r"shaam|शाम|ratri|रात्री|raat|रात|morning|evening|night)\s+(\d{1,2})(?!\S)"
)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")


@dataclass
class Draft:
    """Partially-filled CREATE_REMINDER, carried across turns until complete or abandoned."""

    task: str | None = None
    date: str | None = None
    time: str | None = None  # resolved HH:MM
    ambiguous_hour: tuple[int, int] | None = None  # (hour 1-12, minute) awaiting AM/PM
    period: str | None = None  # day-part said earlier ("सकाळी"); kept until the hour arrives
    meal_after: bool = False  # "after the meal" - which meal not yet known
    meal_delay_min: int = 30

    def missing(self) -> str | None:
        if not self.task:
            return "task"
        if not self.date:
            return "date"
        if self.ambiguous_hour is not None:
            return "ampm"
        if self.meal_after and not self.time:
            return "meal"
        if not self.time:
            return "time"
        return None


@dataclass
class Profile:
    wake_time: str = "07:00"
    lunch_time: str = "13:00"
    dinner_time: str = "20:00"
    language: str = "mr"


@dataclass
class Parsed:
    intent: str
    confidence: float
    language: str
    draft: Draft = field(default_factory=Draft)
    contact_hint: str | None = None
    topic: str | None = None
    query: str = ""  # OPEN_MEDIA / OPEN_WHATSAPP / OPEN_LINK: the words left after the command words


def _add_minutes(hhmm: str, minutes: int) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    total = (h * 60 + m + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _period(norm: str) -> str | None:
    if has_any(norm, PERIOD_NIGHT):
        return "night"
    if has_any(norm, PERIOD_PM):
        return "pm"
    if has_any(norm, PERIOD_AM):
        return "am"
    return None


def _to_24h(hour: int, minute: int, period: str) -> str:
    if period == "am":
        h = 0 if hour == 12 else hour
    elif period == "night":
        h = 0 if hour == 12 else (hour if hour >= 12 else hour + 12)
    else:  # pm / afternoon / evening
        h = hour if hour == 12 else (hour + 12 if hour < 12 else hour)
    return f"{h:02d}:{minute:02d}"


def _parse_date(norm: str, now: datetime) -> str | None:
    m = _ISO.search(norm)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            return None
    for tok in tokens(norm):
        if tok in DATE_WORDS:
            return (now.date() + timedelta(days=DATE_WORDS[tok])).isoformat()
    m = _DMY.search(norm)
    if m:
        try:
            d = date(now.year, int(m[2]), int(m[1]))
            if d < now.date():
                d = date(now.year + 1, d.month, d.day)
            return d.isoformat()
        except ValueError:
            return None
    return None


def _find_hour(norm: str) -> tuple[int, int, bool] | None:
    """Return (hour, minute, is_24h_form) when an explicit clock time is present."""
    m = _HOUR_MARK.search(norm) or _PERIOD_NUM.search(norm)
    if m:
        hour = int(m[1])
        minute = int(m[2]) if m.lastindex and m.lastindex >= 2 and m[2] else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute, hour >= 13 or hour == 0
    m = _HHMM.search(norm)
    if m:
        hour, minute = int(m[1]), int(m[2])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute, hour >= 13 or hour == 0
    return None


def apply_text(draft: Draft, text: str, profile: Profile, now: datetime, is_followup: bool) -> Draft:
    """Merge slots found in `text` into `draft` (returns the same object)."""
    norm = hour_words_to_digits(normalize(text))

    d = _parse_date(norm, now)
    if d:
        draft.date = d

    period = _period(norm)
    if period:
        draft.period = period
    clock = _find_hour(norm)

    if clock is not None:
        hour, minute, is24 = clock
        draft.meal_after = False
        if is24:
            draft.time, draft.ambiguous_hour = f"{hour:02d}:{minute:02d}", None
        elif period or draft.period:
            draft.time, draft.ambiguous_hour = _to_24h(hour, minute, period or draft.period), None
        else:
            draft.time, draft.ambiguous_hour = None, (hour, minute)
    elif draft.ambiguous_hour is not None and period:
        hour, minute = draft.ambiguous_hour
        draft.time, draft.ambiguous_hour = _to_24h(hour, minute, period), None
    elif has_any(norm, MEAL_AFTER) or draft.meal_after:
        draft.meal_after = True
        if has_any(norm, DINNER_WORDS) and not has_any(norm, LUNCH_WORDS):
            draft.time = _add_minutes(profile.dinner_time, draft.meal_delay_min)
        elif has_any(norm, LUNCH_WORDS):
            draft.time = _add_minutes(profile.lunch_time, draft.meal_delay_min)
        # else: leave unresolved -> ask which meal
        if draft.time:
            draft.meal_after = False
    elif period and not draft.time and not _CLOCK_WORD.search(norm):
        # bare day-part ("sakali", "ratri"): configured wake / meal times, never a guess.
        # NOT when a clock word was spoken ("... वाजता") but no hour could be read: that is a
        # clock time, so the wake time must not stand in for it - the time stays open and Arjun asks.
        if period == "am":
            draft.time = profile.wake_time
        elif period == "night":
            draft.time = profile.dinner_time
        elif has_any(norm, LUNCH_WORDS):
            draft.time = profile.lunch_time
        # evening/shaam alone has no configured anchor -> remains missing -> ask

    if not is_followup or not draft.task:
        task = _extract_task(norm)
        if task and not draft.task:
            draft.task = task
    return draft


def _extract_task(norm: str) -> str | None:
    kept: list[str] = []
    for tok in tokens(norm):
        if tok in STOP or tok in DATE_WORDS or tok in YES or tok.isdigit():
            continue
        if _ISO.fullmatch(tok) or _HHMM.fullmatch(tok) or _DMY.fullmatch(tok):
            continue
        kept.append(tok)
    task = " ".join(kept).strip()
    return task or None


def _list_day(norm: str, now: datetime) -> str | None:
    """Which day a "what is on" question is about: None/today, an ISO date, or "ambiguous"."""
    offsets = {DATE_WORDS[t] for t in tokens(norm) if t in DATE_WORDS}
    if len(offsets) > 1:
        return "ambiguous"  # "उद्या आज काय आहे": never guess which one
    if offsets:
        return (now.date() + timedelta(days=offsets.pop())).isoformat()
    return None


def parse(
    text: str,
    profile: Profile,
    now: datetime,
    language: str,
    has_pending: bool,
    pending_action: str | None = None,
) -> Parsed:
    """Classify intent (v1 intents only) and extract reminder slots."""
    norm = normalize(text)
    toks = tokens(norm)
    n = len(toks)

    def done(intent: str, conf: float, draft: Draft | None = None, hint: str | None = None) -> Parsed:
        return Parsed(intent, conf, language, draft or Draft(), hint)

    if not norm:
        return done("UNKNOWN", 0.0)

    if has_any(norm, FORGET):
        return done("FORGET_MEMORY", 0.9)
    if has_any(norm, DECLINE):
        return done("DECLINE_TOPIC", 0.85)

    # Medicine talk is classified before anything else: a "nako"/"nahi" about medicine is a
    # medical decision to deflect, not a topic decline or a cancellation.
    if has_med_word(norm) and not has_any(norm, REMIND):
        if has_any(norm, MED_Q):
            return done("MEDICAL_QUESTION", 0.8)
        if has_any(norm, MED_TAKEN_WORDS) or has_any(norm, DONE):
            return done("MED_TAKEN", 0.8)
        if has_any(norm, SNOOZE_WORDS) or has_any(norm, MINUTE_WORDS):
            return done("MED_SNOOZE", 0.75)
    if has_any(norm, MINUTE_WORDS) and not has_any(norm, REMIND):
        return done("MED_SNOOZE", 0.6)  # "१५ मिनिटांनी सांग"; dispatch checks a dose is due

    # Apps by voice (YouTube, news, WhatsApp, a family link, stop / next / volume). After safety and medicines, before the
    # bare yes/no rules ("बंद कर" would otherwise read as a yes because "कर" is one).
    app = parse_app_command(text, remind=has_any(norm, REMIND))
    if app is not None:
        p = done(app.intent, 0.85)
        # topic = the kind to open ("youtube" | "news_video") or the control word; query / contact_hint = the words
        # left after the command ("भीमसेन जोशींचं भजन", "चंद्रकांतला", a link label).
        p.topic, p.query = app.control or app.topic, app.query
        p.contact_hint = app.query or None
        return p

    if not has_any(norm, REMIND):
        if _HEARING.search(norm):
            return done("HEARING_CHECK", 0.85)
        if has_any(norm, DATE_Q):
            p = done("TIME_QUERY", 0.8)
            p.topic = "date"
            return p
        if has_any(norm, TIME_Q):
            return done("TIME_QUERY", 0.85)
        if has_any(norm, NEXT_Q):
            return done("NEXT_UP", 0.75)

    # While an action awaits its yes/no, an answer made ONLY of yes-words (or only no-words) is that answer at
    # any length: speech recognizers pad a "हो" ("हो हो चालेल हो हो ठेव").
    if has_pending and toks and not has_any(norm, REMIND):
        if all(t in _YES_TOKENS for t in toks):
            return done("CONFIRM_YES", 0.85)
        if all(t in _NO_TOKENS for t in toks):
            return done("CONFIRM_NO", 0.85)

    # short bare answers -> confirmations
    if n <= 4 and not has_any(norm, REMIND):
        if has_any(norm, NO) and not has_any(norm, YES):
            return done("CONFIRM_NO", 0.9)
        if has_any(norm, YES) and not has_any(norm, NO):
            return done("CONFIRM_YES", 0.9)

    # A "no" inside a longer sentence while a reminder (or similar) awaits its yes/no is a correction:
    # cancel it and ask again. Without a pending action, or for a pending story, it stays chat.
    if (
        has_pending
        and pending_action in CORRECTABLE
        and has_any(norm, NO)
        and not has_any(norm, YES)
        and not has_any(norm, REMIND)
    ):
        p = done("CONFIRM_NO", 0.7)
        p.topic = "correction"
        return p

    if has_any(norm, SHARE_VERB) and has_any(norm, FAMILY) and not has_any(norm, REMIND):
        if not has_any(norm, CALL):
            return done("SHARE_STORY_WITH_FAMILY", 0.8)

    if has_any(norm, CALL) and has_any(norm, FAMILY_REL):
        hint = next((t for t in toks if t not in STOP and t not in CALL and len(t) > 2), None)
        return done("CALL_FAMILY_REMINDER", 0.75, hint=hint)

    if has_any(norm, APPOINTMENT) and has_any(norm, QUESTION) and not has_any(norm, REMIND):
        return done("GET_APPOINTMENT", 0.8)

    if has_any(norm, DONE) and not has_any(norm, REMIND):
        return done("COMPLETE_REMINDER", 0.7, hint=_extract_task(norm))

    if has_any(norm, REMIND):
        draft = apply_text(Draft(), text, profile, now, is_followup=False)
        return done("CREATE_REMINDER", 0.8, draft)

    if has_any(norm, LIST_TODAY):
        p = done("LIST_TODAY", 0.8)
        p.topic = _list_day(norm, now)
        return p

    if has_any(norm, APPOINTMENT) and has_any(norm, QUESTION):
        return done("GET_APPOINTMENT", 0.7)

    if has_any(norm, CAREGIVER):
        return done("REQUEST_CAREGIVER", 0.7)

    if n <= 4 and has_any(norm, GREET):
        return done("GREETING", 0.8)

    # bare single-word replies without pending context are not enough to act on
    # "<family link> दाखव" (a generic show/open sentence): the last rule, so every care command wins over it.
    link = parse_app_command(text, remind=False, links=True)
    if link is not None:
        p = done(link.intent, 0.7)
        p.query = link.query
        return p

    if n >= 5:
        return done("CHAT", 0.5)
    return done("UNKNOWN", 0.3)
