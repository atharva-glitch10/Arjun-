import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { confirmThen } from "./guard";
import { startPolling } from "./polling";
import type {
  Anchor,
  Appointment,
  Contact,
  Dose,
  Medicine,
  MedicineInput,
  Note,
  Reminder,
  SharedStory,
  User,
} from "../api";
import { CheckIcon, ClockIcon, CrossIcon, Diya } from "../ghar/Motifs";

interface Data {
  user: User;
  reminders: Reminder[];
  appointments: Appointment[];
  contacts: Contact[];
  book: SharedStory[];
  requests: Note[];
  notes: Note[];
  medicines: Medicine[];
  doses: Dose[];
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

export function Dashboard({ userId, onUser }: { userId: number; onUser: (id: number) => void }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState(() => new Date());

  // quiet = a background refresh: a hiccup must never blank the dashboard (and so never show "Create demo
  // user"); keep the last data and say so in a small banner.
  const load = useCallback(async (quiet = false) => {
    try {
      const [user, reminders, appointments, contacts, book, requests, notes, medicines, doses] =
        await Promise.all([
        api.getUser(userId),
        api.reminders(userId),
        api.appointments(userId),
        api.contacts(userId),
        api.memoryBook(userId),
        api.caregiverRequests(userId),
        api.notifications(userId),
        api.medicines(userId),
        api.medicineDoses(userId, 7),
      ]);
      setData({ user, reminders, appointments, contacts, book, requests, notes, medicines, doses });
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

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await load();
    } catch (e) {
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
  const todayItems = [
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
  const nextAppt = data.appointments.find((a) => parse(a.starts_at) >= now);
  const days = Array.from({ length: 7 }, (_, i) => new Date(now.getTime() - (6 - i) * DAY));
  const requestsToday = data.requests.filter((n) => sameDay(parse(n.created_at), now)).length;
  const name = user.name.replace(/\s*\(synthetic\)\s*$/i, "");

  return (
    <div className="family">
      <div className="family-inner">
        <div className="fam-topbar">
          <Diya size={44} />
          <div style={{ display: "flex", flexDirection: "column" }}>
            <h1 className="h-display" style={{ fontSize: 34, lineHeight: 1.25 }}>
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
          <div className="tile empty">
            <span className="label">BP check</span>
            <span className="value">Not set up</span>
          </div>
          <div className="tile empty">
            <span className="label">Sugar check</span>
            <span className="value">Not set up</span>
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 22, alignItems: "flex-start" }}>
          <section className="fam-card" style={{ flex: "1 1 480px" }}>
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
              Everything here is what Aaji told Arjun. "Done" and "Taken" are self-reported. "On time" is within the window set for each medicine (default 30 min). Meals and walks will appear
              here once they are set up.
            </p>
          </section>

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
              <h2>Health checks</h2>
              <div style={{ padding: "14px 16px", borderRadius: 14, background: "var(--ghar-sand)", display: "flex", flexDirection: "column", gap: 8 }}>
                <span style={{ fontSize: 18, fontWeight: 800 }}>BP and sugar · not set up</span>
                <span style={{ fontSize: 15, lineHeight: 1.5 }}>
                  Turn these on only if Aaji's doctor has asked for home checks (sugar only if she is diabetic). This
                  needs the health-check service, which has not been built yet.
                </span>
              </div>
              <p className="fam-note">
                Arjun records the numbers Aaji reads out and repeats them back to confirm. It never tells her whether a
                reading is good or bad. Please discuss readings with her doctor.
              </p>
            </section>
          </div>
        </div>

        <MedicinesCard
          medicines={data.medicines}
          onAdd={(b) => run(() => api.addMedicine(userId, b))}
          onPatch={(id, b) => run(() => api.patchMedicine(userId, id, b))}
          onDelete={(id) => run(() => api.deleteMedicine(userId, id))}
        />

        <section className="fam-card">
          <h2>Times, interests and consent</h2>
          <div className="fam-form">
            <TimeField label="Wake" value={user.wake_time} onSave={(v) => run(() => api.patchUser(userId, { wake_time: v }))} />
            <TimeField label="Lunch" value={user.lunch_time} onSave={(v) => run(() => api.patchUser(userId, { lunch_time: v }))} />
            <TimeField label="Dinner" value={user.dinner_time} onSave={(v) => run(() => api.patchUser(userId, { dinner_time: v }))} />
            <TimeField label="Chat from" value={user.opener_start} onSave={(v) => run(() => api.patchUser(userId, { opener_start: v }))} />
            <TimeField label="Chat until" value={user.opener_end} onSave={(v) => run(() => api.patchUser(userId, { opener_end: v }))} />
          </div>
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
            Alert me if Arjun notices {name} may be distressed (no conversation content is shared)
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
                  <span style={{ fontWeight: 800 }}>{a.starts_at.replace("T", " ").slice(0, 16)}</span>
                  <span>
                    {a.title} {a.location && `(${a.location})`}
                  </span>
                </li>
              ))}
            </ul>
            <AddAppointment onAdd={(t, s, l) => run(() => api.addAppointment(userId, t, s, l))} />
          </section>

          <section className="fam-card" style={{ flex: "1 1 420px" }}>
            <h2>Family contacts</h2>
            <ul className="fam-list">
              {data.contacts.map((c) => (
                <li key={c.id}>
                  <span style={{ fontWeight: 800 }}>{c.name}</span> ({c.relation}) {c.phone}
                </li>
              ))}
            </ul>
            <AddContact onAdd={(n, r, p) => run(() => api.addContact(userId, n, r, p))} />
          </section>

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

          <section className="fam-card" style={{ flex: "1 1 420px" }}>
            <h2>Requests and alerts</h2>
            {data.requests.length + data.notes.length === 0 && <p>None.</p>}
            <ul className="fam-list">
              {data.requests.map((n) => (
                <li key={`r${n.id}`}>Request: {n.message}</li>
              ))}
              {data.notes.map((n) => (
                <li key={`n${n.id}`}>
                  {n.kind}: {n.body}
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
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
      <input className="fam-input" placeholder="Phone (synthetic only)" aria-label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
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
