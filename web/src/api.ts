export interface User {
  id: number;
  name: string;
  language: "mr" | "hi" | "en" | "bn" | "gu" | "kn" | "ml" | "pa" | "ta" | "te" | "or";
  preferred_languages: User["language"][];
  /** How Arjun addresses her ("" = the name). */
  honorific: string;
  /** Preferred address form used in companion replies. */
  address_as: string;
  age: number | null;
  /** Read-only context: shown to the family, never used for advice. */
  conditions: string[];
  wake_time: string;
  breakfast_time: string;
  lunch_time: string;
  snack_time: string;
  dinner_time: string;
  /** null = not part of her day. */
  walk_time: string | null;
  bp_check_time: string | null;
  /** Optional fasting / after-lunch sugar checks. */
  sugar_check_time: string | null;
  sugar_after_time: string | null;
  /** Her city, used for spoken weather. null = not set (Arjun asks). */
  city: string | null;
  /** Meal / walk / BP / sugar check-ins are spoken only when the family switches this on. */
  daily_checkins: boolean;
  interests: string[];
  opener_start: string;
  opener_end: string;
  consent_distress_alert: boolean;
  speech_style: { rate: "normal" | "slow"; volume: "normal" | "loud"; simple: boolean; companion_name?: string };
}

export interface VoiceMetricStage {
  count: number;
  p50_ms: number | null;
  p90_ms: number | null;
  within_300_ms?: number;
}

export interface VoiceMetrics {
  hours: number;
  counts: { turns: number; complete: number; barge_ins: number };
  stages: {
    stt: VoiceMetricStage;
    final_to_reasoning: VoiceMetricStage;
    reasoning_to_first_audio: VoiceMetricStage;
    eos_to_speaking: VoiceMetricStage;
    barge_in_stop: VoiceMetricStage;
  };
}

export interface SoundEventTrend {
  enabled: boolean;
  days: { date: string; cough_count: number }[];
  total_coughs: number;
}

export interface Reminder {
  id: number;
  task: string;
  due_at: string;
  status: string;
}

export interface Appointment {
  id: number;
  title: string;
  starts_at: string;
  location: string;
  /** 0=Monday..6=Sunday. null = a one-off appointment. */
  weekdays: number[] | null;
  start_time: string | null;
  end_time: string | null;
}

export interface Contact {
  id: number;
  name: string;
  relation: string;
  phone: string;
}

export interface AppLink {
  id: number;
  kind:
    | "youtube_query"
    | "youtube_video"
    | "youtube_playlist"
    | "youtube_channel_live"
    | "youtube_live"
    | "rss"
    | "whatsapp"
    | "link"
    | "app";
  label: string;
  /** whatsapp: the contact id (numbers stay in contacts). */
  value: string;
  spoken_names: string[];
  sort: number;
  /** The family approved a website that is not on the known list: shown with a warning. */
  other_host: boolean;
  /** The same fact with the name the dashboard uses: core-api returns both. */
  approved_by_family?: boolean;
}

export interface AppLinkInput {
  kind: AppLink["kind"];
  label: string;
  value: string;
  spoken_names: string[];
  allow_other_host?: boolean;
}

/** /media/status: the YouTube key lives on core-api; the browser only ever sees whether it is there. */
export interface MediaStatus {
  youtube_key: boolean;
  last_error: string | null;
}

export interface SharedStory {
  id: number;
  summary: string;
  created_at: string;
}

export interface Note {
  id: number;
  kind?: string;
  message?: string;
  body?: string;
  created_at: string;
}

export interface HealthProfile {
  allergies: string[];
  conditions: string[];
  blood_group: string;
  doctor_name: string;
  doctor_contact: string;
  prescription_notes: string;
  emergency_notes: string;
  updated_at: string | null;
}

/** One dose against what the elder SELF-REPORTED. Never verified, never scored. */
export interface DoseCheck {
  dose_id: number;
  medicine_id: number;
  name: string;
  dose: string;
  instructions: string;
  prescribed_by: string;
  due_at: string;
  taken_at: string | null;
  status: string;
  timing: "on_time" | "late" | "pending" | "overdue" | "not_confirmed" | "said_no";
  minutes_late: number | null;
  self_reported: boolean;
}

export type Anchor = "fixed" | "wake" | "lunch" | "dinner";

export interface Medicine {
  id: number;
  name: string;
  dose: string;
  anchor: Anchor;
  time: string | null;
  offset_min: number;
  max_reminders: number;
  repeat_minutes: number;
  window_min: number;
  photo_url: string;
  active: boolean;
  /** From the prescription, verbatim. */
  prescribed_by: string;
  instructions: string;
}
export type MedicineInput = Omit<Medicine, "id">;

export interface Dose {
  id: number;
  medicine_id: number;
  name: string;
  dose: string;
  photo_url: string;
  anchor: Anchor;
  due_at: string;
  status: "due" | "reminded" | "taken" | "unconfirmed";
  reminders_sent: number;
  snoozed_until: string | null;
  taken_at: string | null;
  /** null until taken. Always self-reported. */
  on_time: boolean | null;
}

export interface DueNow {
  current: Dose[];
  next: Dose | null;
}

export interface PendingAction {
  id: number;
  action_type: string;
  payload: Record<string, unknown>;
  status: string;
}

export interface DayItem {
  kind: "reminder" | "appointment" | "medicine" | "meal" | "wake" | "walk" | "bp";
  at: string;
  label: string;
  detail: string;
  status: string;
  ref_id: number | null;
}

/** Server-side view of today. `now` is the household wall clock: the one source of time. */
export interface Day {
  now: string;
  weekday: number;
  part: "morning" | "afternoon" | "evening" | "night";
  items: DayItem[];
  open_now: DayItem[];
  next: DayItem | null;
}

/** One reminder / medicine prompt on its way to the elder. `spoken_at` set = Arjun finished saying it; it is NOT proof she heard it. */
export interface Delivery {
  id: number;
  kind: "reminder" | "medicine" | "checkin";
  ref_id: number;
  attempt: number;
  due_at: string;
  status: "queued" | "speaking" | "spoken" | "shown_only" | "undelivered" | "acknowledged" | "superseded";
  late: boolean;
  /** Reminder task / medicine name, verbatim from SQL. */
  label: string;
  /** Medicine dose, verbatim from SQL ("" for a reminder). */
  detail: string;
  spoken_at: string | null;
  acked_at: string | null;
  outcome: string | null;
  fail_count: number;
}

/** One line of the family's "आजचा दिवस" card. No words of hers, no mood. */
export interface CheckinCardItem {
  kind: string;
  label: string;
  at: string;
  state: "done" | "not_done" | "no_answer" | "asking" | "waiting" | "not_asked";
}

/** When the elder last spoke to Arjun or tapped her screen. Time only: no words are stored. */
export interface Activity {
  last_seen_at: string | null;
  how: "voice" | "tap" | null;
}

export interface WellbeingToday {
  severity: "normal" | "watch" | "urgent" | "emergency";
  mood: string;
  conversations: number;
  last_summary: string;
  last_at: string | null;
}

/** Raw BP numbers only. There is no "level" or judgement anywhere (boundary 7). */
export interface BpReading {
  id: number;
  user_id: number;
  systolic: number;
  diastolic: number;
  pulse: number | null;
  measured_at: string;
  source: "voice" | "watch" | "manual";
}

/** One raw sample from the SYNTHETIC watch. No target and no alert is derived. */
export interface WatchSample {
  id: number;
  user_id: number;
  kind: "heart_rate" | "steps" | "sleep_minutes";
  value: number;
  unit: "bpm" | "steps" | "minutes";
  measured_at: string;
  source: string;
}

/** One thing Arjun remembers about her life (short wording, never a transcript). */
export interface Fact {
  id: number;
  fact: string;
  kind: "person" | "like" | "dislike" | "routine" | "place" | "event" | "concern" | "note";
  source_date: string;
  last_used: string | null;
  confidence: number;
  source: "auto" | "explicit";
}

export interface LivekitToken {
  url: string;
  token: string;
  room: string;
  identity: string;
  expires_in: number;
}

/** A LiveKit token for the family member joining the elder's current room from a Telegram link. */
export interface FamilyJoin {
  url: string;
  token: string;
  room: string;
  identity: string;
  /** Who the elder's page names: the son, else another family member, else "कुटुंब". */
  name: string;
  expires_in: number;
  mode: "voice" | "video";
  call_id: number | null;
}

export interface VideoCall {
  id: number;
  user_id: number;
  contact_id: number;
  contact_name: string;
  mode: "video";
  status: "ringing" | "answered" | "ended" | "missed";
  created_at: string;
}

export interface ClonedVoice {
  id: number;
  name: string;
  relation: string;
  consent_by: string;
  consented_at: string;
  active: boolean;
  use_count: number;
  last_used_at: string | null;
}

export interface ClonedVoiceInput {
  name: string;
  relation: string;
  consent: boolean;
  consent_by: string;
  audio_base64: string;
  mime: string;
}

export interface EmergencySettings {
  help_label: string;
  help_phone: string;
  address: string;
  call_family: boolean;
  calls_enabled?: boolean;
}

export interface EmergencyCallRow {
  stage: "family" | "help";
  target: string;
  phone_tail: string;
  status: "placed" | "failed" | "skipped_disabled" | "skipped_no_number";
  detail: string;
  at: string;
}

async function call<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const core = <T,>(path: string, init?: RequestInit) => call<T>("/core", path, init);
const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  createUser: (name: string) =>
    core<User>("/users", post({ name, language: "mr", interests: ["cooking"] })),
  getUser: (id: number) => core<User>(`/users/${id}`),
  voiceMetrics: (hours = 24) => core<VoiceMetrics>(`/metrics/voice?hours=${hours}`),
  soundEventTrend: (id: number, days = 7) => core<SoundEventTrend>(`/users/${id}/sound-events?days=${days}`),
  patchUser: (id: number, body: Partial<Omit<User, "id" | "name">>) =>
    core<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  reminders: (id: number) => core<Reminder[]>(`/users/${id}/reminders`),
  addReminder: (id: number, task: string, date: string, time: string) =>
    core<Reminder>(`/users/${id}/reminders`, post({ task, date, time })),
  deleteReminder: (id: number, rid: number) =>
    core<void>(`/users/${id}/reminders/${rid}`, { method: "DELETE" }),
  appointments: (id: number) => core<Appointment[]>(`/users/${id}/appointments`),
  addAppointment: (
    id: number,
    title: string,
    startsAt: string,
    location: string,
    weekly?: { weekdays: number[]; start_time: string; end_time?: string },
  ) =>
    core<Appointment>(
      `/users/${id}/appointments`,
      post({ title, starts_at: startsAt, location, ...(weekly ?? {}) }),
    ),
  contacts: (id: number) => core<Contact[]>(`/users/${id}/contacts`),
  addContact: (id: number, name: string, relation: string, phone: string) =>
    core<Contact>(`/users/${id}/contacts`, post({ name, relation, phone })),
  editContact: (id: number, contactId: number, name: string, relation: string, phone: string) =>
    core<Contact>(`/users/${id}/contacts/${contactId}`, { method: "PATCH", body: JSON.stringify({ name, relation, phone }) }),
  deleteContact: (id: number, contactId: number) =>
    core<void>(`/users/${id}/contacts/${contactId}`, { method: "DELETE" }),
  emergencySettings: (id: number) => core<EmergencySettings>(`/users/${id}/emergency-settings`),
  saveEmergencySettings: (id: number, body: EmergencySettings) =>
    core<EmergencySettings>(`/users/${id}/emergency-settings`, { method: "PUT", body: JSON.stringify(body) }),
  emergencyCalls: (id: number) => core<EmergencyCallRow[]>(`/users/${id}/emergency/calls`),
  emergencyLocation: (id: number, body: { lat: number; lon: number; accuracy_m: number }) =>
    core<{ kept: boolean }>(`/users/${id}/emergency/location`, post(body)),
  voices: (id: number) => core<ClonedVoice[]>(`/users/${id}/voices`),
  addVoice: (id: number, body: ClonedVoiceInput) => core<ClonedVoice>(`/users/${id}/voices`, post(body)),
  setVoiceActive: (id: number, voiceId: number, on: boolean) =>
    core<ClonedVoice>(`/users/${id}/voices/${voiceId}/${on ? "activate" : "deactivate"}`, { method: "POST" }),
  deleteVoice: (id: number, voiceId: number) => core<void>(`/users/${id}/voices/${voiceId}`, { method: "DELETE" }),
  voiceLabel: (id: number) => core<{ name: string | null; relation: string | null }>(`/users/${id}/voice-label`),
  appLinks: (id: number) => core<AppLink[]>(`/users/${id}/app-links`),
  mediaStatus: () => core<MediaStatus>("/media/status"),
  /** Other embeddable videos for a title: the player's next candidates when one will not play here. */
  youtubeSearch: (userId: number, q: string) =>
    core<{ video_id: string; title: string; channel: string }[]>(`/media/youtube/search?user_id=${userId}&q=${encodeURIComponent(q)}`),
  addAppLink: (id: number, body: AppLinkInput) => core<AppLink>(`/users/${id}/app-links`, post(body)),
  deleteAppLink: (id: number, linkId: number) => core<void>(`/users/${id}/app-links/${linkId}`, { method: "DELETE" }),
  // Caregiver view: ONLY stories the elder explicitly shared. Never calls /stories.
  memoryBook: (id: number) => core<SharedStory[]>(`/users/${id}/memory-book`),
  // What Arjun knows about her life. Empty unless the family switched "share how she is doing" on (same consent as summaries).
  facts: (id: number) => core<Fact[]>(`/users/${id}/facts?audience=family`),
  deleteFact: (id: number, factId: number) => core<void>(`/users/${id}/facts/${factId}`, { method: "DELETE" }),
  caregiverRequests: (id: number) => core<Note[]>(`/users/${id}/caregiver-requests`),
  notifications: (id: number) => core<Note[]>(`/users/${id}/notifications`),
  activity: (id: number) => core<Activity>(`/users/${id}/activity`),
  wellbeingToday: (id: number) => core<WellbeingToday>(`/users/${id}/wellbeing/today`),
  bpReadings: (id: number) => core<BpReading[]>(`/users/${id}/bp-readings`),
  watchSamples: (id: number) => core<WatchSample[]>(`/users/${id}/watch-samples/latest`),
  medicines: (id: number) => core<Medicine[]>(`/users/${id}/medicines`),
  addMedicine: (id: number, body: MedicineInput) =>
    core<Medicine>(`/users/${id}/medicines`, post(body)),
  patchMedicine: (id: number, mid: number, body: Partial<MedicineInput>) =>
    core<Medicine>(`/users/${id}/medicines/${mid}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteMedicine: (id: number, mid: number) =>
    core<void>(`/users/${id}/medicines/${mid}`, { method: "DELETE" }),
  healthProfile: (id: number) => core<HealthProfile>(`/users/${id}/health-profile`),
  saveHealthProfile: (id: number, body: Omit<HealthProfile, "updated_at">) =>
    core<HealthProfile>(`/users/${id}/health-profile`, { method: "PUT", body: JSON.stringify(body) }),
  medicineCheck: (id: number) => core<DoseCheck[]>(`/users/${id}/medicine-check`),
  medicineDoses: (id: number, days = 7) => core<Dose[]>(`/users/${id}/medicine-doses?days=${days}`),
  dueMedicines: (id: number) => core<DueNow>(`/users/${id}/medicines/due`),
  doseTaken: (id: number, doseId: number) =>
    core<Dose>(`/users/${id}/medicine-doses/${doseId}/taken`, { method: "POST" }),
  doseSnooze: (id: number, doseId: number) =>
    core<Dose>(`/users/${id}/medicine-doses/${doseId}/snooze`, post({ minutes: 15 })),
  day: (id: number) => core<Day>(`/users/${id}/day`),
  pendingAction: (id: number) => core<PendingAction | null>(`/users/${id}/actions/pending`),
  nextAppointment: (id: number) => core<Appointment | null>(`/users/${id}/appointments/next`),
  checkinCard: (id: number) => core<CheckinCardItem[]>(`/users/${id}/checkins/card`),
  openDeliveries: (id: number) => core<Delivery[]>(`/users/${id}/deliveries/open`),
  deliveries: (id: number, days = 1) => core<Delivery[]>(`/users/${id}/deliveries?days=${days}`),
  ackDelivery: (id: number, deliveryId: number, outcome = "ok") =>
    core<Delivery>(`/users/${id}/deliveries/${deliveryId}/ack`, post({ outcome })),
  // A short-lived join token for one voice session (a fresh room each time; the secret stays server-side).
  livekitToken: (userId: number) => core<LivekitToken>("/livekit/token", post({ user_id: userId })),
  // The family-call link from Telegram: checked by core-api, returns a token for the elder's current room.
  familyJoin: (token: string) => core<FamilyJoin>(`/family/join?t=${encodeURIComponent(token)}`),
  familyCallAnswer: (token: string) => core<{ status: string }>("/family/calls/answer", post({ t: token })),
  startVideoCall: (userId: number, contactId: number) =>
    core<VideoCall>(`/users/${userId}/calls`, post({ contact_id: contactId, mode: "video" })),
  sendBriefing: (userId: number, force = false) =>
    core<{ status: string }>(`/users/${userId}/briefing/send`, post({ force })),
  videoCallStatus: (userId: number, callId: number) => core<VideoCall>(`/users/${userId}/calls/${callId}`),
  endVideoCall: (userId: number, callId: number) =>
    core<VideoCall>(`/users/${userId}/calls/${callId}/end`, post({})),
  familyCallEnd: (token: string) => core<{ status: string }>("/family/calls/end", post({ t: token })),
};
