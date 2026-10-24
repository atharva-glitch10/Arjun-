import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { Contact, DueNow, Dose, PendingAction } from "../api";
import {
  ConfirmScreen,
  ConnectingScreen,
  DoneScreen,
  FailedScreen,
  HomeScreen,
  KahaniScreen,
  ListenScreen,
  MedicineScreen,
  ReplyScreen,
  SafetyScreen,
} from "../ghar/Screens";
import type { UpcomingItem } from "../ghar/Screens";
import { FAILURE_TEXT, shownFor } from "../voice/state";
import { useArjunVoice } from "../voice/useArjunVoice";
import {
  dateLine,
  dayBand,
  dayWord,
  greeting,
  isEvening,
  localDate,
  parseNaive,
  periodOfDay,
  spokenTime,
  timeLabel,
  weekday,
} from "./format";

// How the elder is addressed in headings. A family setting later; "आजी" is the design default.
const HONORIFIC = "आजी";

const hhmmOf = (iso: string): string => iso.slice(11, 16);

const toHhmm = (value: unknown): string => (typeof value === "string" ? value.slice(0, 5) : "00:00");

function pendingToCard(p: PendingAction, now: Date) {
  const date = typeof p.payload.date === "string" ? p.payload.date : "";
  const hhmm = toHhmm(p.payload.time);
  const when = localDate(date, hhmm);
  const task = typeof p.payload.task === "string" ? p.payload.task : "";
  return { when, dayLabel: dayBand(when, now), timeText: timeLabel(hhmm), task };
}

/**
 * The elder screen. Everything Arjun hears and says goes through LiveKit + Gnani (see ../voice): this
 * component never uses a browser speech API and never calls reasoning itself. The screen MIRRORS the
 * agent (shownFor); a tapped हो/नको is sent to the agent as text and takes the same path as speech.
 */
export function ElderApp({ userId, forceEvening }: { userId: number; forceEvening?: boolean }) {
  const [now, setNow] = useState(() => new Date());
  // Household clock = server time. skewMs = (server wall clock) - (this device's clock), so a phone
  // with the wrong time or timezone still shows the right time.
  const skewMs = useRef(0);
  const clockNow = () => new Date(Date.now() + skewMs.current);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [items, setItems] = useState<UpcomingItem[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [error, setError] = useState("");
  const [due, setDue] = useState<DueNow>({ current: [], next: null });
  const [medState, setMedState] = useState<"due" | "taken" | "snoozed">("due");
  const [medicineOpen, setMedicineOpen] = useState(false);
  const lastDose = useRef<Dose | null>(null);
  const lastCard = useRef<ReturnType<typeof pendingToCard> | null>(null);
  const queuedText = useRef<string | null>(null);

  const voice = useArjunVoice(userId);
  const shown = shownFor(voice.snapshot);
  const { phase } = voice.snapshot;

  useEffect(() => {
    const id = window.setInterval(() => setNow(clockNow()), 15_000);
    return () => window.clearInterval(id);
  }, []);

  const syncClock = useCallback(async () => {
    try {
      const day = await api.day(userId);
      skewMs.current = parseNaive(day.now).getTime() - Date.now();
      setNow(new Date(Date.now() + skewMs.current));
    } catch {
      // keep the device clock if the server is unreachable
    }
  }, [userId]);

  const loadHome = useCallback(async () => {
    void syncClock();
    try {
      const [reminders, appt, people] = await Promise.all([
        api.reminders(userId),
        api.nextAppointment(userId),
        api.contacts(userId),
      ]);
      setContacts(people);
      const t = clockNow();
      const upcoming: { at: Date; item: UpcomingItem }[] = [];
      for (const r of reminders) {
        const at = parseNaive(r.due_at);
        if (r.status === "done" || at.getTime() < t.getTime() - 60_000) continue;
        const person = people.find((c) => r.task.toLowerCase().includes(c.name.toLowerCase()));
        const hhmm = `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
        const day = dayWord(at, t);
        upcoming.push({
          at,
          item: {
            key: `r${r.id}`,
            when: day === "आज" ? spokenTime(hhmm) : `${day} ${spokenTime(hhmm)}`,
            what: r.task,
            initials: person ? Array.from(person.name)[0] : undefined,
            kind: person ? "call" : "reminder",
          },
        });
      }
      if (appt) {
        const at = parseNaive(appt.starts_at);
        const hhmm = `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
        const day = dayWord(at, t);
        upcoming.push({
          at,
          item: {
            key: `a${appt.id}`,
            when: day === "आज" ? spokenTime(hhmm) : `${day} ${spokenTime(hhmm)}`,
            what: appt.title,
            kind: "appointment",
          },
        });
      }
      upcoming.sort((a, b) => a.at.getTime() - b.at.getTime());
      setItems(upcoming.slice(0, 2).map((u) => u.item));
    } catch {
      // Home still works without the cards; the speak button is the main job.
      setItems([]);
    }
  }, [userId]);

  const pollMedicines = useCallback(async () => {
    try {
      setDue(await api.dueMedicines(userId));
    } catch {
      // medicine data is optional for the home screen
    }
  }, [userId]);

  useEffect(() => {
    void loadHome();
    void pollMedicines();
    const id = window.setInterval(() => void pollMedicines(), 30_000);
    return () => window.clearInterval(id);
  }, [loadHome, pollMedicines]);

  // A due medicine takes over the idle home screen. Until T8 it is SCREEN ONLY and says so
  // (CLAUDE.md boundary 14: never imply a prompt was spoken when it was not).
  const dueDose = due.current[0];
  useEffect(() => {
    if (dueDose && phase === "idle") {
      setMedState("due");
      setMedicineOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dueDose?.id]);

  const medicineTaken = async (d: Dose) => {
    try {
      await api.doseTaken(userId, d.id);
      setMedState("taken");
      void pollMedicines();
    } catch {
      setError("काहीतरी चुकलं. परत प्रयत्न करा.");
    }
  };

  const medicineSnooze = async (d: Dose) => {
    try {
      await api.doseSnooze(userId, d.id);
      setMedState("snoozed");
      void pollMedicines();
    } catch {
      setError("काहीतरी चुकलं. परत प्रयत्न करा.");
    }
  };

  // The confirm card is the pending action from SQL (core-api), never text the agent sent.
  useEffect(() => {
    if (shown !== "confirm") return;
    let live = true;
    api
      .pendingAction(userId)
      .then((p) => {
        if (!live) return;
        setPending(p);
        if (p?.action_type === "CREATE_REMINDER") lastCard.current = pendingToCard(p, clockNow());
      })
      .catch(() => live && setPending(null));
    return () => {
      live = false;
    };
  }, [shown, voice.snapshot.turn, userId]);

  useEffect(() => {
    if (shown === "saved") void loadHome();
  }, [shown, loadHome]);

  // "आज काय?" / "मदत" start a session and then say their words to the agent, like a spoken request.
  useEffect(() => {
    if (phase === "live" && queuedText.current) {
      const text = queuedText.current;
      queuedText.current = null;
      void voice.sendText(text);
    }
  }, [phase]);

  const begin = (text?: string) => {
    setError("");
    queuedText.current = text ?? null;
    void voice.start();
  };

  const toHome = () => {
    voice.stop();
    queuedText.current = null;
    lastCard.current = null;
    setPending(null);
    setMedicineOpen(false);
    setError("");
    void pollMedicines();
    void loadHome();
  };

  const yes = () => void voice.sendText("हो");
  const no = () => void voice.sendText("नाही");

  const evening = forceEvening ?? isEvening(now);
  const shownDose = dueDose ?? lastDose.current;
  if (dueDose) lastDose.current = dueDose;
  const card = pending?.action_type === "CREATE_REMINDER" ? pendingToCard(pending, now) : null;
  const shareNames = contacts.slice(0, 3);
  const tapOpen = phase === "live";

  const body = () => {
    switch (shown) {
      case "connecting":
        return <ConnectingScreen onStop={toHome} />;
      case "failed":
        return (
          <FailedScreen
            message={FAILURE_TEXT[voice.snapshot.failure ?? "dropped"]}
            onRetry={() => begin()}
            onStop={toHome}
          />
        );
      case "safety":
        return <SafetyScreen text={voice.reply} onOk={voice.dismissSafety} />;
      case "listen":
        return <ListenScreen heard={voice.heard} onStop={toHome} />;
      case "confirm":
        if (card)
          return (
            <ConfirmScreen
              dayLabel={card.dayLabel}
              timeLabel={card.timeText}
              task={card.task}
              busy={!tapOpen}
              onYes={yes}
              onNo={no}
            />
          );
        if (pending?.action_type === "SHARE_STORY" && contacts.length > 0)
          return (
            <KahaniScreen
              prompt={voice.reply}
              noteTitle={weekday(now)}
              transcript={voice.heard}
              hint="ऐकतोय… सावकाश सांगा"
              share={{
                names: shareNames.map((c) => c.name),
                initials: shareNames.map((c) => Array.from(c.name)[0] ?? ""),
                busy: !tapOpen,
                onYes: yes,
                onNo: no,
              }}
              onSpeak={() => void voice.start()}
              onBack={toHome}
            />
          );
        return (
          <ReplyScreen
            reply={voice.reply}
            ask="yesno"
            busy={!tapOpen}
            onYes={yes}
            onNo={no}
            onSpeak={() => void voice.start()}
            onOk={toHome}
          />
        );
      case "saved": {
        const c = lastCard.current;
        return (
          <DoneScreen
            title="आठवण ठेवली!"
            line={c ? `${dayWord(c.when, now)} ${periodOfDay(c.when.getHours())} मी तुम्हाला सांगेन` : voice.reply}
            onOk={toHome}
          />
        );
      }
      case "story":
        return (
          <KahaniScreen
            prompt={voice.reply}
            noteTitle={weekday(now)}
            transcript={voice.heard}
            hint="ऐकतोय… सावकाश सांगा"
            onSpeak={() => void voice.start()}
            onBack={toHome}
          />
        );
      case "reply":
        return (
          <ReplyScreen
            reply={voice.reply}
            ask="none"
            onYes={yes}
            onNo={no}
            onSpeak={() => void voice.start()}
            onOk={toHome}
          />
        );
      default:
        if (medicineOpen && shownDose)
          return (
            <MedicineScreen
              status={medState}
              timeLabel={timeLabel(hhmmOf(shownDose.due_at))}
              name={shownDose.name}
              dose={shownDose.dose}
              mealNote={
                shownDose.anchor === "lunch" || shownDose.anchor === "dinner" ? "जेवण झालं ना? मग आता" : undefined
              }
              photoUrl={shownDose.photo_url || undefined}
              nextLine={due.next ? `पुढचं औषध ${timeLabel(hhmmOf(due.next.due_at))}` : "आज आणखी औषध नाही"}
              snoozeUntil={undefined}
              notSpoken
              onTaken={() => void medicineTaken(shownDose)}
              onSnooze={() => void medicineSnooze(shownDose)}
              onOk={toHome}
            />
          );
        return (
          <HomeScreen
            evening={evening}
            greeting={greeting(now, HONORIFIC)}
            dateLine={evening ? `${weekday(now)} · ${periodOfDay(now.getHours())}` : dateLine(now)}
            clock={timeLabel(`${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`)}
            items={items}
            medicine={
              due.next
                ? {
                    when: `${periodOfDay(Number(hhmmOf(due.next.due_at).slice(0, 2)))} · ${timeLabel(hhmmOf(due.next.due_at)).split(" ")[1]}`,
                    name: due.next.name,
                  }
                : undefined
            }
            error={error}
            onSpeak={() => begin()}
            onToday={() => begin("आज काय आहे")}
            onHelp={() => begin("मदत")}
          />
        );
    }
  };

  return (
    <div
      className={`elder-shell${shown === "listen" || shown === "connecting" ? " listening" : evening && shown === "home" ? " night" : ""}`}
    >
      {body()}
    </div>
  );
}
