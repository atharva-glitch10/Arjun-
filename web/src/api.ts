export interface User {
  id: number;
  name: string;
  language: "mr" | "hi" | "en";
  /** How Arjun addresses her ("" = the name). */
  honorific: string;
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
  /** Meal / walk / BP check-ins are spoken only when the family switches this on. */
  daily_checkins: boolean;
  interests: string[];
  opener_start: string;
  opener_end: string;
  consent_distress_alert: boolean;
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
  appLinks: (id: number) => core<AppLink[]>(`/users/${id}/app-links`),
  mediaStatus: () => core<MediaStatus>("/media/status"),
  addAppLink: (id: number, body: AppLinkInput) => core<AppLink>(`/users/${id}/app-links`, post(body)),
  deleteAppLink: (id: number, linkId: number) => core<void>(`/users/${id}/app-links/${linkId}`, { method: "DELETE" }),
  // Caregiver view: ONLY stories the elder explicitly shared. Never calls /stories.
  memoryBook: (id: number) => core<SharedStory[]>(`/users/${id}/memory-book`),
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
};
