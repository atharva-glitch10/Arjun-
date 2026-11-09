import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { activityLine } from "./activity";
import { AppLinksCard } from "./AppLinksCard";
import { KnownFactsCard } from "./KnownFactsCard";
import { EmergencyCard } from "./EmergencyCard";
import { HealthProfileCard } from "./HealthProfileCard";
import { MedicineCheckCard } from "./MedicineCheckCard";
import { NamesCard } from "./NamesCard";
import { VoicesCard } from "./VoicesCard";
import { alarmState, enableAlarm, popup, startAlarm, stopAlarm } from "./alarm";
import { recentEmergencies } from "./alerts";
import { loadAcked, needsPopup, saveAcked, startEmergencyWatch, unacknowledged } from "./emergencyWatch";
import { SEVERITY_LABEL, SEVERITY_RANK, SEVERITY_STYLE, connectFeed, mergeFeed } from "./feed";
import type { FeedEvent, FeedStatus, Severity } from "./feed";
import { dayCardRows, dayCardSummary } from "./daycard";
import { deliveryRows } from "./deliveries";
import { confirmThen } from "./guard";
import { startPolling } from "./polling";
import type {
  WellbeingToday,
  Activity,
  Anchor,
  AppLink,
  Appointment,
  BpReading,
  CheckinCardItem,
  Contact,
  Delivery,
  Dose,
  MediaStatus,
  Medicine,
  MedicineInput,
  Note,
  Reminder,
  SharedStory,
  User,
  VoiceMetrics,
  SoundEventTrend,
  WatchSample,
} from "../api";
import { CheckIcon, ClockIcon, CrossIcon } from "../ghar/Motifs";
import { HeartMark } from "../ghar/Screens";

interface Data {
  user: User;
  reminders: Reminder[];
  appointments: Appointment[];
  nextAppt: Appointment | null;
  contacts: Contact[];
  appLinks: AppLink[];
  mediaStatus: MediaStatus | null;
  book: SharedStory[];
  requests: Note[];
  notes: Note[];
  medicines: Medicine[];
  doses: Dose[];
  deliveries: Delivery[];
  dayCard: CheckinCardItem[];
  activity: Activity;
  today: WellbeingToday;
  bp: BpReading[];
  watch: WatchSample[];
  voiceMetrics: VoiceMetrics | null;
  soundEvents: SoundEventTrend | null;
}

const DAY = 86_400_000;
const parse = (iso: string) => new Date(iso);
const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
const clock = (d: Date) => d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
const shortDay = (d: Date) => d.toLocaleDateString("en-IN", { weekday: "short" });

type Mark = "on-time" | "late" | "missed" | "none";

/** Marks for one medicine on one day. Taken is self-reported; nothing here is a score. */
function doseMark(doses: Dose[], medicineId: number, day: Date, now: Date): Mark {
  const d = doses.find((x) => x.medicine_id === medicineId && sameDay(parse(x.due_at), day));
  if (!d) return "none";
  if (d.status === "taken") return d.on_time ? "on-time" : "late";
  if (d.status === "unconfirmed") return "missed";
  // Still open today: the elder may yet answer, so nothing is marked missed until the family is
  // told (status "unconfirmed") or the day has passed.
  return sameDay(parse(d.due_at), now) ? "none" : "missed";
}

const doseStatus = (d: Dose): string =>
  d.status === "taken"
    ? `Taken${d.on_time ? "" : " late"} (self-reported)`
    : d.status === "unconfirmed"
      ? "Not confirmed"
      : d.status === "reminded"
        ? "Reminded"
        : "Upcoming";

const doseLabel = (d: Dose, now: Date): string =>
  d.status === "due" && parse(d.due_at) <= now ? "Due now" : doseStatus(d);

/** One cell of the 7-day grid. Only what the data supports: done, or past-due and not confirmed. */
function dayMark(reminders: Reminder[], day: Date, now: Date): Mark {
  const due = reminders.filter((r) => sameDay(parse(r.due_at), day) && parse(r.due_at) <= now);
  if (due.length === 0) return "none";
  return due.every((r) => r.status === "done") ? "on-time" : "missed";
}

function MarkCell({ mark }: { mark: Mark }) {
  if (mark === "on-time") {
    return (
      <div className="mark" role="img" aria-label="Done">
        <span className="on-time" style={{ color: "#fff" }}>
          <CheckIcon size={18} w={3} />
        </span>
      </div>
    );
  }
  if (mark === "late") {
    return (
      <div className="mark" role="img" aria-label="Taken late">
        <span className="late" style={{ color: "var(--ghar-ink)" }}>
          <ClockIcon size={18} />
        </span>
      </div>
    );
  }
  if (mark === "missed") {
    return (
      <div className="mark" role="img" aria-label="Not confirmed">
        <span className="missed" style={{ color: "var(--ghar-ink-muted)" }}>
          <CrossIcon />
        </span>
      </div>
    );
  }
  return (
    <div className="mark" role="img" aria-label="Nothing set">
      <span style={{ color: "var(--ghar-miss)" }}>–</span>
    </div>
  );
}

/** One family contact; "Edit" fixes a wrong number (Arjun phones these numbers in an emergency). */
function ContactRow(p: {
  contact: Contact;
  onSave: (name: string, relation: string, phone: string) => Promise<unknown> | void;
  onDelete: () => Promise<unknown> | void;
}) {
  const c = p.contact;
  const [editing, setEditing] = useState(false);
  const [f, setF] = useState({ name: c.name, relation: c.relation, phone: c.phone });
  if (!editing)
    return (
      <li style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <span style={{ flex: 1 }}>
          <span style={{ fontWeight: 800 }}>{c.name}</span> ({c.relation}) {c.phone || "no phone"}
        </span>
        <button className="fbtn" onClick={() => setEditing(true)}>
          Edit
        </button>
      </li>
    );
  return (
    <li style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
      <input className="fam-input" aria-label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
      <input className="fam-input" aria-label="Relation" value={f.relation} onChange={(e) => setF({ ...f, relation: e.target.value })} />
      <input
        className="fam-input"
        aria-label="Phone"
        inputMode="tel"
        placeholder="10-digit phone"
        value={f.phone}
        onChange={(e) => setF({ ...f, phone: e.target.value })}
      />
      <button
        className="fbtn solid"
        disabled={!f.name.trim()}
        onClick={async () => {
          await p.onSave(f.name.trim(), f.relation.trim() || "family", f.phone.trim());
          setEditing(false);
        }}
      >
        Save
      </button>
      <button className="fbtn" onClick={() => setEditing(false)}>
        Cancel
      </button>
      <button
        className="fbtn danger"
        onClick={async () => {
          if (window.confirm(`Remove ${c.name} from contacts?`)) await p.onDelete();
        }}
      >
        Remove
      </button>
    </li>
  );
}

const NOTE_LABEL: Record<string, string> = {
  emergency: "Emergency",
  emergency_location: "Location",
  caregiver_request: "Request",
  lonely: "Lonely",
  distress: "Upset",
  issue: "Problem",
  medicine: "Medicine",
  medicine_unconfirmed: "Medicine",
  delivery: "Not delivered",
};

export function Dashboard({ userId, onUser }: { userId: number; onUser: (id: number) => void }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [briefingStatus, setBriefingStatus] = useState("");
  const [updated, setUpdated] = useState(() => new Date());
  const [tab, setTab] = useState<Tab>("today");

  // quiet = a background refresh: a hiccup must never blank the dashboard (and so never show "Create demo
  // user"); keep the last data and say so in a small banner.
  const load = useCallback(async (quiet = false) => {
    try {
      const [user, reminders, appointments, nextAppt, contacts, book, requests, notes, medicines, doses, deliveries, activity, today, bp, watch, appLinks, mediaStatus, dayCard, voiceMetrics, soundEvents] =
        await Promise.all([
        api.getUser(userId),
        api.reminders(userId),
        api.appointments(userId),
        api.nextAppointment(userId).catch((): Appointment | null => null), // older core-api
        api.contacts(userId),
        api.memoryBook(userId),
        api.caregiverRequests(userId),
        api.notifications(userId),
        api.medicines(userId),
        api.medicineDoses(userId, 7),
        api.deliveries(userId, 1),
        api.activity(userId).catch((): Activity => ({ last_seen_at: null, how: null })), // older core-api
        api.wellbeingToday(userId).catch(
          (): WellbeingToday => ({ severity: "normal", mood: "not_assessed", conversations: 0, last_summary: "", last_at: null }),
        ),
        api.bpReadings(userId).catch((): BpReading[] => []), // older core-api
        api.watchSamples(userId).catch((): WatchSample[] => []), // older core-api
        api.appLinks(userId).catch((): AppLink[] => []), // older core-api
        api.mediaStatus().catch((): MediaStatus | null => null), // older core-api
        api.checkinCard(userId).catch((): CheckinCardItem[] => []), // older core-api
        api.voiceMetrics(24).catch((): VoiceMetrics | null => null),
        api.soundEventTrend(userId, 7).catch((): SoundEventTrend | null => null),
      ]);
      setData({ user, reminders, appointments, nextAppt, contacts, appLinks, mediaStatus, book, requests, notes, medicines, doses, deliveries, dayCard, activity, today, bp, watch, voiceMetrics, soundEvents });
      setUpdated(new Date());
      setError("");
    } catch (e) {
      if (!quiet) setData(null);
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [userId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Refresh every 10 s while visible, and the moment the tab or window comes back.
  useEffect(() => startPolling(() => load(true), 10_000, document, window), [load]);

  // Live feed: WebSocket push, REST polling while the socket is down. A serious row refreshes everything at once.
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [feedStatus, setFeedStatus] = useState<FeedStatus>("connecting");
  useEffect(
    () =>
      connectFeed({
        userId,
        onStatus: setFeedStatus,
        onEvents: (rows) => {
          setFeed((have) => mergeFeed(have, rows));
          if (rows.some((e) => SEVERITY_RANK[e.severity] >= SEVERITY_RANK.watch)) void load(true);
        },
      }),
    [userId, load],
  );

  // Emergency alarm: checked every 15 s EVEN WHEN THIS TAB IS IN THE BACKGROUND (the refresh above pauses
  // then). Rings (sound + pop-up + tab title) until someone taps "I have seen it" on this device.
  const acked = useRef<Set<number>>(loadAcked(safeStorage()));
  const popped = useRef<Set<number>>(new Set());
  const [ringing, setRinging] = useState<number[]>([]);
  const [alarm, setAlarm] = useState(() => alarmState());
  useEffect(() => {
    const stop = startEmergencyWatch(async () => {
      const notes = await api.notifications(userId);
      const open = unacknowledged(notes, acked.current, new Date());
      for (const n of needsPopup(open, popped.current)) {
        popup(n.id, n.body ?? "Emergency reported");
        popped.current.add(n.id);
      }
      setRinging(open.map((n) => n.id));
      if (open.length > 0) {
        startAlarm();
        void load(true); // show the red banner now, even if the normal refresh is paused
      } else {
        stopAlarm();
      }
    }, 15_000);
    return () => {
      stop();
      stopAlarm();
    };
  }, [userId, load]);
  const acknowledge = () => {
    ringing.forEach((id) => acked.current.add(id));
    saveAcked(safeStorage(), acked.current);
    setRinging([]);
    stopAlarm();
  };

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    }
  };

  const sendBriefingNow = async () => {
    setBriefingStatus("सारांश पाठवत आहे…");
    try {
      const result = await api.sendBriefing(userId, true);
      setBriefingStatus(result.status === "sent" ? "सारांश Telegram वर पाठवला." : "सारांश पाठवता आला नाही.");
      await load(true);
    } catch (e) {
      setBriefingStatus("सारांश पाठवता आला नाही.");
      setError(e instanceof Error ? e.message : "Request failed");
    }
  };

  if (!data) {
    return (
      <div className="family">
        <div className="family-inner">
          <div className="fam-card">
            <h2>Aaji's day</h2>
            <p role="status">{error || "Loading..."}</p>
            <div>
              <button
                className="fbtn solid"
                onClick={() =>
                  void confirmThen(
                    (m) => window.confirm(m),
                    "The demo uses ONE synthetic user (user 1). Creating another splits the data between users. Create anyway?",
                    () => api.createUser("Demo Aaji (synthetic)").then((u) => onUser(u.id)),
                  )
                }
              >
                Create demo user
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const { user } = data;
  const now = new Date();
  const marker = (label: string, hhmm: string, detail: string) => {
    const at = new Date(now);
    at.setHours(Number(hhmm.slice(0, 2)), Number(hhmm.slice(3, 5)), 0, 0);
    return { at, label, detail, status: "Family-set", ok: false };
  };
  const todayItems = [
    marker("Wake", user.wake_time, "Family-set time"),
    marker("Breakfast", user.breakfast_time, "Family-set meal"),
    marker("Lunch", user.lunch_time, "Family-set meal"),
    marker("Snack", user.snack_time, "Family-set meal"),
    marker("Dinner", user.dinner_time, "Family-set meal"),
    ...(user.walk_time ? [marker("Walk", user.walk_time, "Family-set time")] : []),
    ...(user.bp_check_time ? [marker("BP check", user.bp_check_time, "Family-set time")] : []),
    ...data.reminders
      .filter((r) => sameDay(parse(r.due_at), now))
      .map((r) => ({
        at: parse(r.due_at),
        label: r.task,
        detail: "Reminder",
        // "fired" = due time passed; it is NOT spoken on the elder device until voice delivery (T8) exists.
        status: r.status === "done" ? "Done" : r.status === "fired" ? "Due · not spoken yet" : "Upcoming",
        ok: r.status === "done",
      })),
    ...data.appointments
      .filter((a) => sameDay(parse(a.starts_at), now))
      .map((a) => ({
        at: parse(a.starts_at),
        label: a.title,
        detail: a.location ? `Appointment · ${a.location}` : "Appointment",
        status: "Appointment",
        ok: false,
      })),
    ...data.doses
      .filter((d) => sameDay(parse(d.due_at), now))
      .map((d) => ({
        at: parse(d.due_at),
        label: `${d.name} · ${d.dose}`,
        detail: `Medicine · set for ${clock(parse(d.due_at))}`,
        status: doseLabel(d, now),
        ok: d.status === "taken",
      })),
  ].sort((a, b) => a.at.getTime() - b.at.getTime());

  const todayDoses = data.doses.filter((d) => sameDay(parse(d.due_at), now));
  const dosesTaken = todayDoses.filter((d) => d.status === "taken").length;
  const activeMeds = data.medicines.filter((x) => x.active);

  const todayReminders = data.reminders.filter((r) => sameDay(parse(r.due_at), now));
  const doneToday = todayReminders.filter((r) => r.status === "done").length;
  const nextAppt = data.nextAppt;
  const latestBp = data.bp[0] ?? null;
  const watchLabel: Record<WatchSample["kind"], string> = {
    heart_rate: "Heart rate",
    steps: "Steps",
    sleep_minutes: "Sleep",
  };
  const days = Array.from({ length: 7 }, (_, i) => new Date(now.getTime() - (6 - i) * DAY));
  const requestsToday = data.requests.filter((n) => sameDay(parse(n.created_at), now)).length;
  const name = user.name.replace(/\s*\(synthetic\)\s*$/i, "");
  const emergencies = recentEmergencies(data.notes, now);
  const seen = activityLine(data.activity.last_seen_at, now, user.wake_time, name);

  return (
    <div className="family">
      <div className="family-inner">
        {emergencies.map((n) => (
          <div
            key={`alert${n.id}`}
            role="alert"
            style={{
              background: "var(--ghar-kumkum)",
              color: "#fff",
              padding: "14px 18px",
              borderRadius: 12,
              fontSize: 20,
              lineHeight: 1.45,
              fontWeight: 700,
            }}
          >
            {n.body}
            <div style={{ fontSize: 16, fontWeight: 400, marginTop: 4 }}>{parse(n.created_at).toLocaleString("en-IN")}</div>
            {ringing.includes(n.id) && (
              <button
                className="fbtn"
                style={{ marginTop: 10, background: "#fff", color: "var(--ghar-kumkum)", borderColor: "#fff", fontWeight: 800 }}
                onClick={acknowledge}
              >
                I have seen it - stop the alarm
              </button>
            )}
          </div>
        ))}
        <div className="fam-note fam-alarm">
          {alarm.sound && alarm.popup ? (
            <span>
              <strong style={{ color: "var(--ghar-leaf)" }}>Emergency alarm is on</strong> (sound and pop-up). Keep this
              tab open; in a background tab it can take up to a minute. No call or SMS is sent.
            </span>
          ) : (
            <>
              <button className="fbtn solid" onClick={() => void enableAlarm().then(setAlarm)}>
                Turn on emergency alarm
              </button>
              <span>
                Rings with sound and a pop-up even when this tab is in the background.
                {alarm.sound && !alarm.popup && " Pop-ups are blocked in this browser; sound only."}
                {!alarm.sound && " Browsers need one tap for sound after every page load."}
              </span>
            </>
          )}
        </div>
        <div className="fam-topbar fam-header">
          <HeartMark size={56} />
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span className="fam-brand">Arjun · family</span>
            <h1 className="fam-title">
              {name}'s day
            </h1>
            <span className="t-muted" style={{ fontSize: 17 }}>
              {now.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short" })} · updated {clock(updated)}
              {error && (
                <strong role="status" style={{ marginLeft: 8, color: "var(--ghar-kumkum)" }}>
                  · could not refresh, showing the last data
                </strong>
              )}
            </span>
          </div>
          <span className="grow" />
          <button className="fbtn solid" onClick={() => void sendBriefingNow()}>
            आत्ता सारांश पाठवा
          </button>
          {briefingStatus && <span role="status" className="t-muted">{briefingStatus}</span>}
          <div className="pill" style={{ fontSize: 17, alignSelf: "center" }}>
            {requestsToday === 0 ? (
              <>
                <span style={{ color: "var(--ghar-leaf)" }}>
                  <CheckIcon size={20} w={2.4} />
                </span>
                No help requests today
              </>
            ) : (
              <>
                <span style={{ color: "var(--ghar-kumkum)" }}>
                  <ClockIcon size={20} />
                </span>
                {requestsToday} help request{requestsToday > 1 ? "s" : ""} today
              </>
            )}
          </div>
          <button className="fbtn" onClick={() => void load()}>
            Refresh
          </button>
        </div>

        {error && (
          <p className="error-note" role="alert">
            {error}
          </p>
        )}

        <nav className="fam-tabs" role="tablist" aria-label="Dashboard sections">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>

        {tab === "today" && (
          <>
        <div className="fam-hero">
          <section
            className="fam-card"
            aria-label={`How is ${name} today`}
            style={{ borderLeft: `10px solid ${SEVERITY_STYLE[data.today.severity].bg}` }}
          >
            <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center" }}>
              <h2 style={{ margin: 0 }}>How is {name} today</h2>
              <SeverityChip level={data.today.severity} />
              {data.today.mood !== "not_assessed" && <span className="pill" style={{ fontSize: 17 }}>Mood: {data.today.mood}</span>}
              <span className="grow" />
              <span className="t-muted" style={{ fontSize: 15 }}>
                {feedStatus === "live" ? "Live" : feedStatus === "polling" ? "Updating every 5 s" : "Connecting..."}
              </span>
            </div>
            <p style={{ fontSize: 19, lineHeight: 1.5, margin: "10px 0 6px" }}>
              {data.today.last_summary ||
                (user.consent_distress_alert
                  ? "No conversation summary yet today."
                  : `Summaries and mood are off. Turn on "share how ${name} is doing" below to see them.`)}
            </p>
            <span className={`fam-seen ${seen.tone}`}>{seen.text}</span>
            <span className="t-muted" style={{ fontSize: 15 }}>
              {data.today.conversations} conversation{data.today.conversations === 1 ? "" : "s"} today · summaries, never
              her exact words
            </span>
            {feed.length > 0 && (
              <ul className="fam-list" style={{ marginTop: 12 }}>
                {feed.slice(0, 12).map((e) => (
                  <li key={`f${e.id}`}>
                    <SeverityChip level={e.severity} small />
                    <span style={{ fontWeight: 800, minWidth: 64 }}>{clock(parse(e.created_at))}</span>
                    <span style={{ flex: 1 }}>
                      <strong>{e.title}</strong> {e.body}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <BeforeYouCall name={name} summary={data.today.last_summary} book={data.book} feed={feed} />

        </div>

        <div className="tiles">
          <div className="tile">
            <span className="label">Reminders today</span>
            <span className="value">
              {todayReminders.length === 0 ? "None set" : `${doneToday} of ${todayReminders.length} done`}
            </span>
          </div>
          <div className="tile">
            <span className="label">Next appointment</span>
            <span className="value">
              {nextAppt ? `${shortDay(parse(nextAppt.starts_at))} · ${clock(parse(nextAppt.starts_at))}` : "None"}
            </span>
          </div>
          <div className="tile">
            <span className="label">Memory Book</span>
            <span className="value">{data.book.length} shared</span>
          </div>
          {activeMeds.length === 0 ? (
            <div className="tile empty">
              <span className="label">Medicines</span>
              <span className="value">Not set up</span>
            </div>
          ) : (
            <div className="tile">
              <span className="label">Medicines</span>
              <span className="value">
                {todayDoses.length === 0 ? "None due today" : `${dosesTaken} of ${todayDoses.length} taken`}
              </span>
              <span className="label">self-reported</span>
            </div>
          )}
          {latestBp && (
            <div className="tile">
              <span className="label">Last BP (raw numbers)</span>
              <span className="value">{latestBp.systolic} / {latestBp.diastolic}</span>
            </div>
          )}
        </div>


        <div className="fam-cols">
          <section className="fam-card">
            <h2>Today</h2>
            {todayItems.length === 0 && <p className="fam-note">Nothing scheduled for today.</p>}
            {todayItems.map((t, i) => (
              <div className="timeline-row" key={i}>
                <span className="time">{clock(t.at)}</span>
                <div style={{ flexGrow: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                  <span className="label">{t.label}</span>
                  <span className="detail">{t.detail}</span>
                </div>
                <span className={`status${t.ok ? " ok" : ""}`}>{t.status}</span>
              </div>
            ))}
            <p className="fam-note">
              Everything here is what {name} told Arjun. "Done" and "Taken" are self-reported. "On time" is within the window set for each medicine (default 30 min). Meals, the walk and the BP check are the family-set times above; nothing is scored.
            </p>
          </section>

          <div className="fam-stack">
            <section className="fam-card" aria-label="Requests and alerts">
              <h2>Requests and alerts</h2>
              {data.requests.length + data.notes.length === 0 && <p>None.</p>}
              <ul className="fam-list">
                {data.requests.map((n) => (
                  <li key={`r${n.id}`}>
                    <span>
                      <strong>Request:</strong> {n.message}
                    </span>
                  </li>
                ))}
                {data.notes
                  .filter((n) => !(n.kind === "caregiver_request" && data.requests.some((r) => r.message === n.body)))
                  .map((n) => (
                    <li key={`n${n.id}`}>
                      <span>
                        <strong>{NOTE_LABEL[n.kind ?? ""] ?? "Note"}:</strong> {n.body}
                      </span>
                    </li>
                  ))}
              </ul>
            </section>
            <section className="fam-card">
              <h2>Spoken reminders and medicines</h2>
              {deliveryRows(data.deliveries).length === 0 && <p className="fam-note">Nothing was due today.</p>}
              {deliveryRows(data.deliveries).map((r) => (
                <div className="timeline-row" key={r.id}>
                  <span className="time">{clock(parse(r.dueAt))}</span>
                  <div style={{ flexGrow: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                    <span className="label">{r.title}</span>
                    <span className="detail">{r.kind}</span>
                  </div>
                  <span className={`status${r.tone === "ok" ? " ok" : ""}`}>{r.text}</span>
                </div>
              ))}
              <p className="fam-note">
                "Spoken" means Arjun finished saying it, not that Aaji heard it. "Taken" is what Aaji told Arjun. "Not
                delivered" means it did not reach Aaji by voice (no open session, or the speech was interrupted or failed
                3 times); it stays on her screen until she taps OK.
              </p>
            </section>

          </div>
        </div>
          </>
        )}

        {tab === "health" && (
          <>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 22, alignItems: "flex-start" }}>
          <div style={{ flex: "1 1 420px", minWidth: 0, display: "flex", flexDirection: "column", gap: 22 }}>
            <section className="fam-card">
              <h2>This week</h2>
              <div style={{ overflowX: "auto" }}>
                <div style={{ minWidth: 380, display: "flex", flexDirection: "column", gap: 8 }}>
                  <div className="week-grid">
                    <span />
                    {days.map((d) => (
                      <span className="head" key={d.toDateString()}>
                        {shortDay(d)}
                      </span>
                    ))}
                  </div>
                  {activeMeds.map((med) => (
                    <div className="week-grid" key={med.id}>
                      <span style={{ fontSize: 16, fontWeight: 600 }}>{med.name}</span>
                      {days.map((d) => (
                        <MarkCell key={d.toDateString()} mark={doseMark(data.doses, med.id, d, now)} />
                      ))}
                    </div>
                  ))}
                  <div className="week-grid">
                    <span style={{ fontSize: 16, fontWeight: 600 }}>Reminders</span>
                    {days.map((d) => (
                      <MarkCell key={d.toDateString()} mark={dayMark(data.reminders, d, now)} />
                    ))}
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 16, fontSize: 15 }} className="t-muted">
                <span>● green check = on time</span>
                <span>● haldi clock = late</span>
                <span>○ cross = not confirmed</span>
                <span>– = nothing set</span>
              </div>
            </section>

            <section className="fam-card">
              <h2>Synthetic watch</h2>
              {data.watch.length === 0 ? (
                <p className="fam-note">No samples yet. This is a synthetic feed; no watch is paired.</p>
              ) : (
                <ul className="fam-list">
                  {data.watch.map((x) => (
                    <li key={x.id}>
                      <span style={{ fontWeight: 800, minWidth: 110 }}>{watchLabel[x.kind]}</span>
                      <span style={{ flex: 1 }}>
                        {x.value} {x.unit}
                      </span>
                      <span className="t-muted">
                        {clock(parse(x.measured_at))} · {x.source}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="fam-note">
                Raw samples from a made-up watch feed for the demo. There is no target, score or alert, and nothing here
                is a medical reading.
              </p>
            </section>

            <section className="fam-card">
              <h2>Health checks</h2>
              <div style={{ padding: "14px 16px", borderRadius: 14, background: "var(--ghar-sand)", display: "flex", flexDirection: "column", gap: 8 }}>
                <span style={{ fontSize: 18, fontWeight: 800 }}>
                  BP readings · raw numbers only
                </span>
                {data.bp.length === 0 ? (
                  <span style={{ fontSize: 15, lineHeight: 1.5 }}>
                    {user.bp_check_time
                      ? `The BP check is in her day at ${user.bp_check_time}. No reading has been recorded yet.`
                      : "The BP check is not in her day. Add a time under “Her day” to ask her to check it."}
                  </span>
                ) : (
                  <ul className="fam-list">
                    {data.bp.slice(0, 5).map((x) => (
                      <li key={x.id}>
                        <span style={{ fontWeight: 800 }}>
                          {x.systolic} / {x.diastolic}
                        </span>
                        <span className="t-muted">
                          {clock(parse(x.measured_at))} · {x.source}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <span style={{ fontSize: 15, lineHeight: 1.5 }}>
                  Sugar checks are not set up. This needs the health-check service, which exists for BP only.
                </span>
              </div>
              <p className="fam-note">
                Arjun records the numbers Aaji reads out and repeats them back. It never says whether a reading is
                good or bad, and there is no target or range here. Please discuss readings with her doctor.
              </p>
            </section>
          </div>
        </div>

        <HealthProfileCard userId={userId} name={name} />
        <MedicineCheckCard userId={userId} name={name} />
        <MedicinesCard
          medicines={data.medicines}
          onAdd={(b) => run(() => api.addMedicine(userId, b))}
          onPatch={(id, b) => run(() => api.patchMedicine(userId, id, b))}
          onDelete={(id) => run(() => api.deleteMedicine(userId, id))}
        />

        {data.user.daily_checkins && (
            <section className="fam-card" aria-label="आजचा दिवस">
              <h2>आजचा दिवस</h2>
              <p className="fam-note" style={{ marginTop: 0 }}>
                {data.user.daily_checkins ? dayCardSummary(data.dayCard) : "Day check-ins are switched off (Settings)."}
              </p>
              {dayCardRows(data.dayCard).map((r) => (
                <div className="timeline-row" key={r.key}>
                  <span className="time">{r.time}</span>
                  <div style={{ flexGrow: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                    <span className="label">{r.title}</span>
                  </div>
                  <span className="status" title={r.words} aria-label={r.words}>
                    {r.mark}
                  </span>
                </div>
              ))}
              <p className="fam-note">
                ✅ done, ❌ not done, — asked but no answer, … asked and waiting, ○ later today, · never asked. These are what Aaji told
                Arjun (self-reported). Her words are never shown here. How she is feeling appears above only if she
                agreed to share it.
              </p>
            </section>

        )}
          </>
        )}

        {tab === "settings" && (
          <>
        <NamesCard user={user} onSave={(patch) => run(() => api.patchUser(userId, patch))} />

        <EmergencyCard userId={userId} name={name} />

        <section className="fam-card">
          <h2>Her day (family-set times)</h2>
          <div className="fam-form" aria-label="Speech preferences">
            <label>Speaking pace
              <select value={user.speech_style?.rate ?? "normal"} onChange={(e) => run(() => api.patchUser(userId, { speech_style: { ...user.speech_style, rate: e.target.value as "normal" | "slow" } }))}>
                <option value="normal">Normal</option><option value="slow">Slow</option>
              </select>
            </label>
            <label>Arjun volume
              <select value={user.speech_style?.volume ?? "normal"} onChange={(e) => run(() => api.patchUser(userId, { speech_style: { ...user.speech_style, volume: e.target.value as "normal" | "loud" } }))}>
                <option value="normal">Normal</option><option value="loud">Loud</option>
              </select>
            </label>
            <label><input type="checkbox" checked={user.speech_style?.simple ?? false} onChange={(e) => run(() => api.patchUser(userId, { speech_style: { ...user.speech_style, simple: e.target.checked } }))} /> Use simpler wording</label>
          </div>
          <div className="fam-form">
            <TimeField label="Wake" value={user.wake_time} onSave={(v) => run(() => api.patchUser(userId, { wake_time: v }))} />
            <TimeField label="Breakfast" value={user.breakfast_time} onSave={(v) => run(() => api.patchUser(userId, { breakfast_time: v }))} />
            <TimeField label="Lunch" value={user.lunch_time} onSave={(v) => run(() => api.patchUser(userId, { lunch_time: v }))} />
            <TimeField label="Snack" value={user.snack_time} onSave={(v) => run(() => api.patchUser(userId, { snack_time: v }))} />
            <TimeField label="Dinner" value={user.dinner_time} onSave={(v) => run(() => api.patchUser(userId, { dinner_time: v }))} />
            <OptionalTimeField label="Walk" value={user.walk_time} onSave={(v) => run(() => api.patchUser(userId, { walk_time: v }))} />
            <OptionalTimeField label="BP check" value={user.bp_check_time} onSave={(v) => run(() => api.patchUser(userId, { bp_check_time: v }))} />
            <OptionalTimeField label="Sugar (fasting)" value={user.sugar_check_time} onSave={(v) => run(() => api.patchUser(userId, { sugar_check_time: v }))} />
            <OptionalTimeField label="Sugar (after lunch)" value={user.sugar_after_time} onSave={(v) => run(() => api.patchUser(userId, { sugar_after_time: v }))} />
            <TimeField label="Chat from" value={user.opener_start} onSave={(v) => run(() => api.patchUser(userId, { opener_start: v }))} />
            <TimeField label="Chat until" value={user.opener_end} onSave={(v) => run(() => api.patchUser(userId, { opener_end: v }))} />
          </div>
          <label style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 16, fontWeight: 700 }}>
            <input
              type="checkbox"
              style={{ width: 24, height: 24 }}
              checked={user.daily_checkins}
              onChange={(e) => run(() => api.patchUser(userId, { daily_checkins: e.target.checked }))}
            />
            Daily health check-ins: {user.daily_checkins ? "ON" : "OFF"} — Arjun asks about meals, water, the walk,
            BP and sugar at the times above (she answers; nothing is scored)
          </label>
          <div className="fam-form">
            <TextField
              label="Age"
              initial={user.age === null ? "" : String(user.age)}
              onSave={(v) => run(() => api.patchUser(userId, { age: v.trim() ? Number(v) : null }))}
            />
            <TextField
              label="Conditions (comma separated; shown to the family, never used for advice)"
              initial={user.conditions.join(", ")}
              onSave={(v) =>
                run(() => api.patchUser(userId, { conditions: v.split(",").map((s) => s.trim()).filter(Boolean) }))
              }
            />
            <TextField
              label="City (for the weather Arjun tells her)"
              initial={user.city ?? ""}
              onSave={(v) => run(() => api.patchUser(userId, { city: v.trim() || null }))}
            />
          </div>
        </section>

        <section className="fam-card">
          <h2>Interests and consent</h2>
          <TextField
            label="Interests (comma separated)"
            initial={user.interests.join(", ")}
            onSave={(v) =>
              run(() => api.patchUser(userId, { interests: v.split(",").map((s) => s.trim()).filter(Boolean) }))
            }
          />
          <label style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 16 }}>
            <input
              type="checkbox"
              style={{ width: 24, height: 24 }}
              checked={user.consent_distress_alert}
              onChange={(e) => run(() => api.patchUser(userId, { consent_distress_alert: e.target.checked }))}
            />
            Share how {name} is doing: mood, conversation summaries, and alerts if she seems distressed or says she feels
            lonely or mentions a health complaint (never her exact words; a physical emergency and a help request always alert)
          </label>
          <MotionSetting />
        </section>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 22, alignItems: "flex-start" }}>
          <section className="fam-card" style={{ flex: "1 1 420px" }}>
            <h2>Reminders</h2>
            <ul className="fam-list">
              {data.reminders.map((r) => (
                <li key={r.id}>
                  <span style={{ fontWeight: 800 }}>{r.due_at.replace("T", " ").slice(0, 16)}</span>
                  <span style={{ flex: 1 }}>{r.task}</span>
                  <span className={`status${r.status === "done" ? " ok" : ""}`}>{r.status}</span>
                  <button className="fbtn danger" onClick={() => void run(() => api.deleteReminder(userId, r.id))}>
                    Delete
                  </button>
                </li>
              ))}
            </ul>
            <AddReminder onAdd={(t, d, tm) => run(() => api.addReminder(userId, t, d, tm))} />
          </section>

          <section className="fam-card" style={{ flex: "1 1 420px" }}>
            <h2>Appointments</h2>
            <ul className="fam-list">
              {data.appointments.map((a) => (
                <li key={a.id}>
                  <span style={{ fontWeight: 800 }}>
                    {a.weekdays === null
                      ? a.starts_at.replace("T", " ").slice(0, 16)
                      : `Every ${a.weekdays.map((d) => ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d]).join(", ")} · ${a.start_time}${a.end_time ? `-${a.end_time}` : ""}`}
                  </span>
                  <span>
                    {a.title} {a.location && a.location !== a.title && `(${a.location})`}
                  </span>
                </li>
              ))}
            </ul>
            <AddAppointment onAdd={(t, s, l) => run(() => api.addAppointment(userId, t, s, l))} />
          </section>


        </div>
        <details className="fam-card fam-tech">
          <summary>For the team: voice speed and sound events</summary>
          <div className="fam-cols">
            <section className="fam-card" aria-label="Voice performance">
              <h2>Voice performance</h2>
              <VoicePerformance metrics={data.voiceMetrics} />
            </section>

            <section className="fam-card" aria-label="Cough trend">
              <h2>Sound events</h2>
              <p className="fam-note">{data.soundEvents?.enabled ? `Cough events, last 7 days · ${data.soundEvents.total_coughs} total` : "Detection is off"}</p>
              <div style={{ display: "flex", alignItems: "end", gap: 8, minHeight: 72 }} aria-label="Daily cough counts">
                {(data.soundEvents?.days ?? []).map((day) => {
                  const peak = Math.max(1, ...(data.soundEvents?.days ?? []).map((item) => item.cough_count));
                  return <div key={day.date} title={`${day.date}: ${day.cough_count}`} style={{ flex: 1, textAlign: "center" }}>
                    <span style={{ display: "block", height: `${Math.max(4, (day.cough_count / peak) * 48)}px`, background: "#b5c9b9", borderRadius: 6 }} />
                    <small>{day.cough_count}</small>
                  </div>;
                })}
              </div>
            </section>

          </div>
        </details>
          </>
        )}

        {tab === "family" && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 22, alignItems: "flex-start" }}>
          <section className="fam-card" style={{ flex: "1 1 420px" }}>
            <h2>Family contacts</h2>
            <ul className="fam-list">
              {data.contacts.map((c) => (
                <ContactRow
                  key={c.id}
                  contact={c}
                  onSave={(n, r, p) => run(() => api.editContact(userId, c.id, n, r, p))}
                  onDelete={() => run(() => api.deleteContact(userId, c.id))}
                />
              ))}
            </ul>
            <AddContact onAdd={(n, r, p) => run(() => api.addContact(userId, n, r, p))} />
          </section>

          <AppLinksCard
            links={data.appLinks}
            contacts={data.contacts}
            mediaStatus={data.mediaStatus}
            onAdd={(body) => run(() => api.addAppLink(userId, body))}
            onDelete={(id) => run(() => api.deleteAppLink(userId, id))}
          />

          <VoicesCard userId={userId} name={name} />

          <KnownFactsCard userId={userId} consent={data.user.consent_distress_alert} name={name} />

          <section className="fam-card" style={{ flex: "1 1 420px" }}>
            <h2>Memory Book</h2>
            <p className="fam-note">Only stories {name} chose to share.</p>
            {data.book.length === 0 && <p>Nothing shared yet.</p>}
            <ul className="fam-list">
              {data.book.map((s) => (
                <li key={s.id}>{s.summary}</li>
              ))}
            </ul>
          </section>
        </div>
        )}
      </div>
    </div>
  );
}


function VoicePerformance({ metrics }: { metrics: VoiceMetrics | null }) {
  const rows = metrics
    ? [
        ["STT", metrics.stages.stt],
        ["Final → reasoning", metrics.stages.final_to_reasoning],
        ["Reasoning → audio", metrics.stages.reasoning_to_first_audio],
        ["EOS → speaking", metrics.stages.eos_to_speaking],
        ["Barge-in stop", metrics.stages.barge_in_stop],
      ] as const
    : [];
  const maximum = Math.max(1, ...rows.flatMap(([, stage]) => [stage.p50_ms ?? 0, stage.p90_ms ?? 0]));
  const width = (value: number | null) => `${Math.max(value === null ? 0 : 3, Math.min(100, ((value ?? 0) / maximum) * 100))}%`;
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div className="fam-note">Last 24 h · {metrics?.counts.turns ?? 0} turns · {metrics?.counts.barge_ins ?? 0} interruptions</div>
      {rows.map(([label, stage]) => (
        <div key={label} style={{ display: "grid", gridTemplateColumns: "minmax(120px, 1fr) 2fr auto", gap: 12, alignItems: "center" }}>
          <strong>{label}</strong>
          <div style={{ display: "grid", gap: 4 }} aria-hidden="true">
            <span style={{ display: "block", height: 7, width: width(stage.p50_ms), background: "#437a58", borderRadius: 8 }} />
            <span style={{ display: "block", height: 7, width: width(stage.p90_ms), background: "#b5c9b9", borderRadius: 8 }} />
          </div>
          <span className="label" style={{ whiteSpace: "nowrap" }}>
            {stage.p50_ms ?? "—"} / {stage.p90_ms ?? "—"} ms
          </span>
          <span className="fam-note" style={{ gridColumn: "2 / 4", marginTop: -8 }}>p50 / p90 · n={stage.count}</span>
        </div>
      ))}
      {metrics?.counts.barge_ins ? (
        <div className="fam-note">≤300 ms: {metrics.stages.barge_in_stop.within_300_ms ?? 0}/{metrics.counts.barge_ins}</div>
      ) : null}
    </div>
  );
}

type Tab = "today" | "health" | "family" | "settings";
const TABS: [Tab, string][] = [
  ["today", "Today"],
  ["health", "Health & medicines"],
  ["family", "Family & memories"],
  ["settings", "Settings"],
];

// Talking points for the family's next call, built only from what this dashboard already shows (today's
// summary, stories she chose to share, today's non-routine feed titles). Nothing new is collected.
function BeforeYouCall({ name, summary, book, feed }: { name: string; summary: string; book: SharedStory[]; feed: FeedEvent[] }) {
  const points = [
    ...(summary ? [summary] : []),
    ...book.slice(0, 2).map((b) => `Ask about her story: ${b.summary}`),
    ...feed.filter((e) => SEVERITY_RANK[e.severity] >= SEVERITY_RANK.watch).slice(0, 2).map((e) => `Check in on: ${e.title}`),
  ].slice(0, 4);
  return (
    <section className="fam-card call-card" aria-label={`Before you call ${name}`}>
      <h2>Before you call {name}</h2>
      {points.length === 0 ? (
        <p className="fam-note" style={{ marginTop: 0 }}>
          Nothing new yet. After she chats with Arjun, the main points to talk about show up here.
        </p>
      ) : (
        <ul className="call-points">
          {points.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function MotionSetting() {
  const [off, setOff] = useState(() => {
    try {
      return localStorage.getItem("arjun_reduce_motion") === "1";
    } catch {
      return false;
    }
  });
  const change = (v: boolean) => {
    setOff(v);
    document.documentElement.classList.toggle("no-motion", v);
    try {
      localStorage.setItem("arjun_reduce_motion", v ? "1" : "0");
    } catch {
      // storage unavailable: setting applies for this session only
    }
  };
  return (
    <label style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 16 }}>
      <input type="checkbox" style={{ width: 24, height: 24 }} checked={off} onChange={(e) => change(e.target.checked)} />
      Turn off animations (this device only)
    </label>
  );
}

function TimeField({ label, value, onSave }: { label: string; value: string; onSave: (v: string) => void }) {
  return (
    <label className="fam-field">
      {label}
      <input className="fam-input" type="time" defaultValue={value} onBlur={(e) => e.target.value && onSave(e.target.value)} />
    </label>
  );
}

function TextField({ label, initial, onSave }: { label: string; initial: string; onSave: (v: string) => void }) {
  return (
    <label className="fam-field">
      {label}
      <input className="fam-input" defaultValue={initial} onBlur={(e) => onSave(e.target.value)} style={{ maxWidth: 420 }} />
    </label>
  );
}

/** An optional family-set time: unticked means "not part of her day". */
function OptionalTimeField({
  label,
  value,
  onSave,
}: {
  label: string;
  value: string | null;
  onSave: (v: string | null) => void;
}) {
  return (
    <label className="fam-field">
      {label}
      <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          className="fam-input"
          type="time"
          defaultValue={value ?? ""}
          disabled={value === null}
          onBlur={(e) => {
            if (e.target.value) onSave(e.target.value);
          }}
        />
        <input
          type="checkbox"
          style={{ width: 24, height: 24 }}
          checked={value !== null}
          aria-label={`${label} is part of her day`}
          onChange={(e) => onSave(e.target.checked ? (value ?? "09:00") : null)}
        />
      </span>
    </label>
  );
}

function AddReminder({ onAdd }: { onAdd: (task: string, date: string, time: string) => void }) {
  const [task, setTask] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  return (
    <form
      className="fam-form"
      onSubmit={(e) => {
        e.preventDefault();
        onAdd(task, date, time);
        setTask("");
      }}
    >
      <input className="fam-input" required placeholder="Task" aria-label="Task" value={task} onChange={(e) => setTask(e.target.value)} />
      <input className="fam-input" required type="date" aria-label="Date" value={date} onChange={(e) => setDate(e.target.value)} />
      <input className="fam-input" required type="time" aria-label="Time" value={time} onChange={(e) => setTime(e.target.value)} />
      <button className="fbtn solid" type="submit">
        Add reminder
      </button>
    </form>
  );
}

function AddAppointment({ onAdd }: { onAdd: (title: string, startsAt: string, loc: string) => void }) {
  const [title, setTitle] = useState("");
  const [at, setAt] = useState("");
  const [loc, setLoc] = useState("");
  return (
    <form
      className="fam-form"
      onSubmit={(e) => {
        e.preventDefault();
        onAdd(title, at, loc);
        setTitle("");
      }}
    >
      <input className="fam-input" required placeholder="Title" aria-label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <input className="fam-input" required type="datetime-local" aria-label="Date and time" value={at} onChange={(e) => setAt(e.target.value)} />
      <input className="fam-input" placeholder="Place" aria-label="Place" value={loc} onChange={(e) => setLoc(e.target.value)} />
      <button className="fbtn solid" type="submit">
        Add appointment
      </button>
    </form>
  );
}

function AddContact({ onAdd }: { onAdd: (name: string, rel: string, phone: string) => void }) {
  const [name, setName] = useState("");
  const [rel, setRel] = useState("son");
  const [phone, setPhone] = useState("");
  return (
    <form
      className="fam-form"
      onSubmit={(e) => {
        e.preventDefault();
        onAdd(name, rel, phone);
        setName("");
        setPhone("");
      }}
    >
      <input className="fam-input" required placeholder="Name" aria-label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <input className="fam-input" placeholder="Relation" aria-label="Relation" value={rel} onChange={(e) => setRel(e.target.value)} />
      <input className="fam-input" placeholder="Phone (10 digits)" aria-label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <button className="fbtn solid" type="submit">
        Add contact
      </button>
    </form>
  );
}

const ANCHORS: { value: Anchor; label: string }[] = [
  { value: "fixed", label: "At a fixed time" },
  { value: "wake", label: "After waking" },
  { value: "lunch", label: "After lunch" },
  { value: "dinner", label: "After dinner" },
];

function scheduleText(m: Medicine): string {
  if (m.anchor === "fixed") return `Every day at ${m.time ?? "?"}`;
  const label = ANCHORS.find((a) => a.value === m.anchor)?.label.toLowerCase() ?? m.anchor;
  return `${label} + ${m.offset_min} min`;
}

function MedicinesCard({
  medicines,
  onAdd,
  onPatch,
  onDelete,
}: {
  medicines: Medicine[];
  onAdd: (b: MedicineInput) => void;
  onPatch: (id: number, b: Partial<MedicineInput>) => void;
  onDelete: (id: number) => void;
}) {
  const blank: MedicineInput = {
    name: "",
    dose: "",
    anchor: "fixed",
    time: "09:00",
    offset_min: 30,
    max_reminders: 3,
    repeat_minutes: 15,
    window_min: 30,
    photo_url: "",
    active: true,
    prescribed_by: "",
    instructions: "",
  };
  const [form, setForm] = useState<MedicineInput>(blank);
  const set = <K extends keyof MedicineInput>(k: K, v: MedicineInput[K]) => setForm({ ...form, [k]: v });

  return (
    <section className="fam-card">
      <h2>Medicines</h2>
      <p className="fam-note">
        Only you can add or change medicines. Arjun reads the name and dose back exactly as you type them here, never
        rephrased, and does not answer questions about them: it says to ask the doctor and offers to tell you. Enter
        what the doctor prescribed; this is not medical advice.
      </p>
      {medicines.length === 0 && <p>No medicines set up.</p>}
      <ul className="fam-list">
        {medicines.map((m) => (
          <li key={m.id}>
            <span style={{ fontWeight: 800 }}>{m.name}</span>
            <span>{m.dose}</span>
            {m.instructions && <span className="t-muted">{m.instructions}</span>}
            {m.prescribed_by && <span className="t-muted">Prescribed by {m.prescribed_by}</span>}
            <span className="t-muted">
              {scheduleText(m)} · asks up to {m.max_reminders}× every {m.repeat_minutes} min
            </span>
            <span style={{ flex: 1 }} />
            <span className={`status${m.active ? " ok" : ""}`}>{m.active ? "Active" : "Paused"}</span>
            <button className="fbtn" onClick={() => onPatch(m.id, { active: !m.active })}>
              {m.active ? "Pause" : "Resume"}
            </button>
            <button
              className="fbtn danger"
              onClick={() => {
                if (window.confirm(`Delete ${m.name} and its history?`)) onDelete(m.id);
              }}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
      <form
        className="fam-form"
        onSubmit={(e) => {
          e.preventDefault();
          onAdd({ ...form, time: form.anchor === "fixed" ? form.time : null });
          setForm(blank);
        }}
      >
        <label className="fam-field">
          Name (as on the strip)
          <input className="fam-input" required value={form.name} onChange={(e) => set("name", e.target.value)} />
        </label>
        <label className="fam-field">
          Prescribed by (doctor)
          <input className="fam-input" value={form.prescribed_by} onChange={(e) => set("prescribed_by", e.target.value)} />
        </label>
        <label className="fam-field">
          Instructions (as on the prescription)
          <input className="fam-input" maxLength={300} value={form.instructions} onChange={(e) => set("instructions", e.target.value)} />
        </label>
        <label className="fam-field">
          Dose (exactly as prescribed)
          <input className="fam-input" required value={form.dose} onChange={(e) => set("dose", e.target.value)} />
        </label>
        <label className="fam-field">
          When
          <select className="fam-input" value={form.anchor} onChange={(e) => set("anchor", e.target.value as Anchor)}>
            {ANCHORS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        {form.anchor === "fixed" ? (
          <label className="fam-field">
            Time
            <input
              className="fam-input"
              required
              type="time"
              value={form.time ?? ""}
              onChange={(e) => set("time", e.target.value)}
            />
          </label>
        ) : (
          <label className="fam-field">
            Minutes after
            <input
              className="fam-input"
              type="number"
              min={0}
              max={240}
              value={form.offset_min}
              onChange={(e) => set("offset_min", Number(e.target.value))}
              style={{ width: 90 }}
            />
          </label>
        )}
        <label className="fam-field">
          Ask up to (times)
          <input
            className="fam-input"
            type="number"
            min={1}
            max={10}
            value={form.max_reminders}
            onChange={(e) => set("max_reminders", Number(e.target.value))}
            style={{ width: 90 }}
          />
        </label>
        <label className="fam-field">
          Photo of strip (link, optional)
          <input className="fam-input" type="url" value={form.photo_url} onChange={(e) => set("photo_url", e.target.value)} />
        </label>
        <button className="fbtn solid" type="submit" style={{ alignSelf: "flex-end" }}>
          Add medicine
        </button>
      </form>
      <p className="fam-note">
        If a medicine is not confirmed after the set number of reminders, only you are notified. Arjun never scolds and
        keeps no streaks.
      </p>
    </section>
  );
}

/** localStorage, or undefined where it is missing or throws (private mode, some embedded browsers). */
function safeStorage(): Storage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

function SeverityChip({ level, small }: { level: Severity; small?: boolean }) {
  const st = SEVERITY_STYLE[level];
  return (
    <span
      style={{
        background: st.bg,
        color: st.fg,
        borderRadius: 999,
        padding: small ? "2px 10px" : "6px 14px",
        fontSize: small ? 14 : 18,
        fontWeight: 800,
        whiteSpace: "nowrap",
      }}
    >
      {SEVERITY_LABEL[level]}
    </span>
  );
}
