import re
from datetime import date as Date
from datetime import datetime
from datetime import time as Time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
Lang = Literal["mr", "hi", "en", "bn", "gu", "kn", "ml", "pa", "ta", "te", "or"]


class SpeechStyle(BaseModel):
    rate: Literal["normal", "slow"] = "normal"
    volume: Literal["normal", "loud"] = "normal"
    simple: bool = False
    # What she calls Arjun (family-set, Settings). Blank = "Arjun". Letters in any script, spaces, dots only.
    companion_name: str = Field(default="", max_length=24, pattern=r"^[^\d<>{}\[\]@#$%^&*=+|\\/~`\"]*$")


def _check_hhmm(v: str | None) -> str | None:
    if v is not None and not HHMM.match(v):
        raise ValueError("must be HH:MM (24h)")
    return v


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    language: Lang = "mr"
    preferred_languages: list[Lang] = Field(default_factory=list, max_length=10)
    wake_time: str = "07:00"
    lunch_time: str = "13:00"
    dinner_time: str = "20:00"
    breakfast_time: str = "08:00"
    snack_time: str = "17:00"
    walk_time: str | None = None  # optional: None = no daily walk in her day
    bp_check_time: str | None = None
    sugar_check_time: str | None = None  # fasting sugar check (optional)
    sugar_after_time: str | None = None  # after-lunch sugar check (optional)
    city: str | None = Field(default=None, max_length=80)  # her city, for spoken weather
    daily_checkins: bool = False  # meal / walk / BP check-ins are spoken only when the family switches this on
    honorific: str = Field(default="", max_length=60)
    address_as: str | None = Field(default=None, max_length=60)
    age: int | None = Field(default=None, ge=0, le=120)
    conditions: list[str] = []
    interests: list[str] = []
    opener_start: str = "10:00"
    opener_end: str = "18:00"
    consent_distress_alert: bool = False
    speech_style: "SpeechStyle" = Field(default_factory=lambda: SpeechStyle())

    _v = field_validator(
        "wake_time", "lunch_time", "dinner_time", "breakfast_time", "snack_time", "walk_time", "bp_check_time",
        "sugar_check_time", "sugar_after_time",
        "opener_start", "opener_end",
    )(_check_hhmm)


class UserPatch(BaseModel):
    language: Lang | None = None
    preferred_languages: list[Lang] | None = Field(default=None, max_length=10)
    wake_time: str | None = None
    lunch_time: str | None = None
    dinner_time: str | None = None
    breakfast_time: str | None = None
    snack_time: str | None = None
    walk_time: str | None = None
    bp_check_time: str | None = None
    sugar_check_time: str | None = None
    sugar_after_time: str | None = None
    city: str | None = Field(default=None, max_length=80)
    daily_checkins: bool | None = None
    honorific: str | None = Field(default=None, max_length=60)
    address_as: str | None = Field(default=None, max_length=60)
    age: int | None = Field(default=None, ge=0, le=120)
    conditions: list[str] | None = None
    interests: list[str] | None = None
    opener_start: str | None = None
    opener_end: str | None = None
    consent_distress_alert: bool | None = None
    speech_style: "SpeechStyle | None" = None

    _v = field_validator(
        "wake_time", "lunch_time", "dinner_time", "breakfast_time", "snack_time", "walk_time", "bp_check_time",
        "sugar_check_time", "sugar_after_time",
        "opener_start", "opener_end",
    )(_check_hhmm)


class UserOut(UserIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    address_as: str


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    relation: str = "family"
    phone: str = ""


class ContactOut(ContactIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ReminderIn(BaseModel):
    task: str = Field(min_length=1, max_length=200)
    date: Date
    time: Time
    time_ambiguous: bool = False


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task: str
    due_at: datetime
    status: str


class AppointmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    location: str = ""
    # Optional weekly rule: weekdays 0=Monday..6=Sunday. `starts_at` is then the first day it applies.
    weekdays: list[int] | None = None
    start_time: str | None = None
    end_time: str | None = None

    _v = field_validator("start_time", "end_time")(_check_hhmm)

    @model_validator(mode="after")
    def _weekly_rule(self) -> "AppointmentIn":
        if self.weekdays is None:
            return self
        if not self.weekdays or any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("weekdays must be a non-empty list of 0..6")
        if not self.start_time:
            raise ValueError("start_time is required for a weekly appointment")
        if self.end_time and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        self.weekdays = sorted(set(self.weekdays))
        return self


class AppointmentOut(AppointmentIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ProposeIn(BaseModel):
    # No medicine create/edit type exists on purpose: only the family dashboard changes medicines.
    action_type: Literal[
        "CREATE_REMINDER",
        "COMPLETE_REMINDER",
        "REQUEST_CAREGIVER",
        "SHARE_STORY",
        "SAVE_STORY",
        "MEDICINE_TAKEN",
        "MEDICINE_SNOOZE",
    ]
    payload: dict = {}  # type: ignore[type-arg]


class PendingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action_type: str
    payload: dict  # type: ignore[type-arg]
    status: str


class StoryIn(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)


class StoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    summary: str
    share_status: str
    created_at: datetime


class SharedStoryOut(BaseModel):
    """What caregivers may see: only explicitly shared stories."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    summary: str
    created_at: datetime


class DistressOut(BaseModel):
    caregiver_alerted: bool


class SoundEventIn(BaseModel):
    label: Literal["cough", "scream", "crying", "bang"]
    confidence: float = Field(ge=0.0, le=1.0)


Anchor = Literal["fixed", "wake", "breakfast", "lunch", "dinner"]


class MedicineIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    dose: str = Field(min_length=1, max_length=100)
    anchor: Anchor = "fixed"
    time: str | None = None  # HH:MM, required when anchor == "fixed"
    offset_min: int = Field(default=30, ge=0, le=240)
    max_reminders: int = Field(default=3, ge=1, le=10)
    repeat_minutes: int = Field(default=15, ge=5, le=120)
    window_min: int = Field(default=30, ge=5, le=180)
    photo_url: str = Field(default="", max_length=500)
    active: bool = True
    prescribed_by: str = Field(default="", max_length=100)
    instructions: str = Field(default="", max_length=300)

    _v = field_validator("time")(_check_hhmm)

    @field_validator("name", "dose")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("photo_url")
    @classmethod
    def _photo(cls, v: str) -> str:
        v = v.strip()
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("photo_url must be an http(s) URL")
        return v

    @model_validator(mode="after")
    def _fixed_needs_time(self) -> "MedicineIn":
        if self.anchor == "fixed" and not self.time:
            raise ValueError("time is required when anchor is 'fixed'")
        if self.anchor != "fixed":
            self.time = None
        return self


class MedicinePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    dose: str | None = Field(default=None, min_length=1, max_length=100)
    anchor: Anchor | None = None
    time: str | None = None
    offset_min: int | None = Field(default=None, ge=0, le=240)
    max_reminders: int | None = Field(default=None, ge=1, le=10)
    repeat_minutes: int | None = Field(default=None, ge=5, le=120)
    window_min: int | None = Field(default=None, ge=5, le=180)
    photo_url: str | None = Field(default=None, max_length=500)
    active: bool | None = None
    prescribed_by: str | None = Field(default=None, max_length=100)
    instructions: str | None = Field(default=None, max_length=300)

    _v = field_validator("time")(_check_hhmm)


class MedicineOut(MedicineIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DoseOut(BaseModel):
    id: int
    medicine_id: int
    name: str
    dose: str
    photo_url: str
    anchor: str  # fixed | wake | lunch | dinner (lets the elder screen say "after your meal")
    due_at: datetime
    status: str  # due | reminded | taken | unconfirmed
    reminders_sent: int
    snoozed_until: datetime | None
    taken_at: datetime | None
    on_time: bool | None  # None until taken. Self-reported either way.


class DueOut(BaseModel):
    current: list[DoseOut]  # due now (not snoozed); the elder screen shows the first
    next: DoseOut | None  # next upcoming dose today


class SnoozeIn(BaseModel):
    minutes: int = Field(default=15, ge=5, le=60)


class CheckinOut(BaseModel):
    id: int
    user_id: int
    kind: str  # sleep | breakfast | lunch | walk | interest | home | dinner | bp | appt<ID> | rem<ID>
    ref: str = ""
    due_at: datetime
    status: str  # pending | asked | done | skipped | missed | unanswered
    asked_at: datetime | None
    answered_at: datetime | None
    followups: int
    postponed: int = 0
    source: str = "asked"
    heard: bool  # a voice session really spoke (or showed) the prompt for this check-in


class CheckinCardItem(BaseModel):
    """One line of the family's "आजचा दिवस" card. No words of hers, only what happened."""

    kind: str  # sleep | breakfast | lunch | medicine | appointment | reminder | walk | interest | home | dinner | bp
    label: str  # medicine name / appointment title / contact first name; "" otherwise
    at: datetime  # when it was answered, else when it was due
    state: str  # done | not_done | no_answer | asking | waiting | not_asked


class CheckinAnswer(BaseModel):
    answer: Literal["done", "skipped"]
    mood: Literal["good", "low"] | None = None


class CheckinVolunteer(BaseModel):
    """She said it on her own ("जेवले"): the matching check-in is answered and will not be asked."""

    topic: Literal["sleep", "breakfast", "lunch", "snack", "walk", "dinner", "home"]
    answer: Literal["done", "skipped"] = "done"


class BpReadingIn(BaseModel):
    """Raw numbers only. No target, range or judgement is accepted (boundary 7)."""

    systolic: int = Field(ge=40, le=300)
    diastolic: int = Field(ge=20, le=200)
    pulse: int | None = Field(default=None, ge=20, le=250)
    source: Literal["voice", "watch", "manual"] = "voice"

    @model_validator(mode="after")
    def _systolic_above_diastolic(self) -> "BpReadingIn":
        if self.systolic <= self.diastolic:
            raise ValueError("systolic must be above diastolic")
        return self


class BpReadingOut(BpReadingIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    measured_at: datetime


class WatchSampleIn(BaseModel):
    """A raw sample from the synthetic watch. The unit is derived from the kind, never sent or judged."""

    kind: Literal["heart_rate", "steps", "sleep_minutes"]
    value: int = Field(ge=0, le=200_000)


class WatchSampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    kind: str
    value: int
    unit: str
    measured_at: datetime
    source: str


class DayItem(BaseModel):
    kind: Literal["reminder", "appointment", "medicine", "meal", "wake", "walk", "bp", "sugar"]
    at: datetime
    label: str  # task / title / medicine name verbatim; meal: breakfast|lunch|snack|dinner; wake|walk|bp|sugar
    detail: str = ""  # medicine dose verbatim, or appointment place
    status: str  # pending|fired|done, scheduled, due|reminded|taken|unconfirmed
    ref_id: int | None = None


class DayOut(BaseModel):
    now: datetime
    weekday: int  # 0 = Monday
    part: Literal["morning", "afternoon", "evening", "night"]
    items: list[DayItem]  # everything today, in time order (SQL only)
    open_now: list[DayItem]  # already due and not yet done / taken
    next: DayItem | None  # next thing still ahead today
