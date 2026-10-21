import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { Contact, DueNow, Dose, PendingAction } from "../api";
import {
  ConfirmScreen,
  DoneScreen,
  HomeScreen,
  KahaniScreen,
  ListenScreen,
  MedicineScreen,
  ReplyScreen,
} from "../ghar/Screens";
import type { UpcomingItem } from "../ghar/Screens";
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
import { recognitionAvailable, speak, startListening, stopSpeaking } from "./speech";
import type { Listener } from "./speech";

type Screen = "home" | "listen" | "confirm" | "saved" | "reply" | "story" | "medicine";

// How the elder is addressed in headings. A family setting later; "आजी" is the design default.
const HONORIFIC = "आजी";

interface Turn {
  reply: string;
  intent: string;
  mode: string;
  language: string;
  awaiting: boolean;
}

const hhmmOf = (iso: string): string => iso.slice(11, 16);

/** Fixed template: name and dose are SQL text, spoken exactly as the family entered them. */
const medicineLine = (d: Dose): string => `औषधाची वेळ. ${d.name}. ${d.dose}. घेतली का?`;

const toHhmm = (value: unknown): string => (typeof value === "string" ? value.slice(0, 5) : "00:00");

function pendingToCard(p: PendingAction, now: Date) {
  const date = typeof p.payload.date === "string" ? p.payload.date : "";
  const hhmm = toHhmm(p.payload.time);
  const when = localDate(date, hhmm);
  const task = typeof p.payload.task === "string" ? p.payload.task : "";
  return { when, dayLabel: dayBand(when, now), timeText: timeLabel(hhmm), task };
}

export function ElderApp({ userId, forceEvening }: { userId: number; forceEvening?: boolean }) {
  const [now, setNow] = useState(() => new Date());
  // Household clock = server time. skewMs = (server wall clock) - (this device's clock), so a phone
  // with the wrong time or timezone still shows and speaks the right time.
  const skewMs = useRef(0);
  const clockNow = () => new Date(Date.now() + skewMs.current);
  const [screen, setScreen] = useState<Screen>("home");
  const [heard, setHeard] = useState("");
  const [turn, setTurn] = useState<Turn | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [items, setItems] = useState<UpcomingItem[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [savedLine, setSavedLine] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const [due, setDue] = useState<DueNow>({ current: [], next: null });
  const [medState, setMedState] = useState<"due" | "taken" | "snoozed">("due");
  const announced = useRef<number | null>(null);

  const listener = useRef<Listener | null>(null);
  const busyRef = useRef(false);
  const lastDose = useRef<Dose | null>(null);
  const screenRef = useRef<Screen>("home");
  const pendingRef = useRef<PendingAction | null>(null);
  const lang = turn?.language ?? "mr";

  const go = (s: Screen) => {
    screenRef.current = s;
    setScreen(s);
  };

  const stopListener = () => {
    listener.current?.stop();
    listener.current = null;
  };

  useEffect(() => {
    const id = window.setInterval(() => setNow(clockNow()), 15_000);
    return () => {
      window.clearInterval(id);
      stopListener();
      stopSpeaking();
    };
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

  // A due medicine takes over the home screen (never interrupts a conversation in progress).
  const dueDose = due.current[0];
  useEffect(() => {
    if (dueDose && screenRef.current === "home") {
      setMedState("due");
      go("medicine");
      if (announced.current !== dueDose.id) {
        announced.current = dueDose.id;
        sayThenListen(medicineLine(dueDose), "mr", true);
      }
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
      // snooze limit reached or already handled: tell the family via voice flow instead
      void submit("१५ मिनिटांनी सांग");
    }
  };

  /** Speak, then (optionally) listen once for a spoken answer: a yes/no, or the next chat turn. */
  const sayThenListen = (text: string, language: string, answer: boolean) => {
    speak(text, language, () => {
      if (!answer || !recognitionAvailable()) return;
      if (screenRef.current === "home" || screenRef.current === "listen") return;
      stopListener();
      listener.current = startListening(
        (spoken, final) => {
          if (spoken) setHeard(spoken);
          if (final && spoken) void submit(spoken);
        },
        () => {
          listener.current = null;
        },
        language,
      );
    });
  };

  const submit = async (text: string) => {
    const said = text.trim();
    if (!said || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    const from = screenRef.current;
    if (from === "listen" || from === "home") setHeard(said);
    stopListener();
    const prev = pendingRef.current;
    try {
      const res = await api.turn(userId, said);
      const t: Turn = {
        reply: res.reply,
        intent: res.intent,
        mode: res.mode,
        language: res.language,
        awaiting: res.awaiting_confirmation,
      };
      setTurn(t);

      let next: Screen = "reply";
      let nextPending: PendingAction | null = null;
      let say = res.reply;
      let listenForAnswer = false;

      if (res.mode === "safety") {
        next = "reply";
      } else if (res.awaiting_confirmation) {
        nextPending = await api.pendingAction(userId);
        listenForAnswer = true;
        if (nextPending?.action_type === "CREATE_REMINDER") next = "confirm";
        else if (nextPending?.action_type === "SHARE_STORY" && contacts.length > 0) next = "story";
        else next = "reply";
      } else if (prev?.action_type === "CREATE_REMINDER" && res.intent === "CONFIRM_YES") {
        const card = pendingToCard(prev, now);
        setSavedLine(`${dayWord(card.when, now)} ${periodOfDay(card.when.getHours())} मी तुम्हाला सांगेन`);
        next = "saved";
        void loadHome();
      } else if (prev?.action_type === "CREATE_REMINDER" && res.intent === "CONFIRM_NO") {
        next = "listen";
        say = "";
      } else if (res.mode === "companion") {
        next = "story";
        // Keep the conversation going hands-free. It ends on silence, "नको", or the back button.
        listenForAnswer = res.intent === "CHAT";
      }

      pendingRef.current = nextPending;
      setPending(nextPending);
      go(next);
      if (next === "listen") {
        setHeard("");
        beginListening();
      } else {
        sayThenListen(say, res.language, listenForAnswer);
      }
      if (from === "home" && next === "reply" && !res.awaiting_confirmation) void loadHome();
    } catch {
      setError("काहीतरी चुकलं. परत प्रयत्न करा.");
      go(from === "listen" ? "listen" : "home");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const beginListening = () => {
    setError("");
    stopListener();
    stopSpeaking();
    go("listen");
    setHeard("");
    if (!recognitionAvailable()) return; // listen screen shows a text box as a fallback
    listener.current = startListening(
      (text) => setHeard(text),
      (failed) => {
        listener.current = null;
        if (failed) setError("ऐकू आलं नाही. परत सांगा.");
      },
      "mr",
    );
  };

  const toHome = () => {
    void pollMedicines();
    stopListener();
    stopSpeaking();
    pendingRef.current = null;
    setPending(null);
    setTurn(null);
    setHeard("");
    setError("");
    go("home");
    void loadHome();
  };

  const evening = forceEvening ?? isEvening(now);
  const shownDose = dueDose ?? lastDose.current;
  if (dueDose) lastDose.current = dueDose;
  const card = pending?.action_type === "CREATE_REMINDER" ? pendingToCard(pending, now) : null;
  const shareNames = contacts.slice(0, 3);

  return (
    <div className={`elder-shell${screen === "listen" ? " listening" : evening && screen === "home" ? " night" : ""}`}>
      {screen === "home" && (
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
          busy={busy}
          error={error}
          onSpeak={beginListening}
          onToday={() => void submit("आज काय आहे")}
          onHelp={() => void submit("मदत")}
        />
      )}
      {screen === "listen" && (
        <>
          <ListenScreen
            heard={heard}
            onDone={() => void submit(heard)}
            onStop={toHome}
            onType={recognitionAvailable() ? undefined : { value: typed, set: setTyped, send: () => {
              void submit(typed);
              setTyped("");
            } }}
          />
          {error && (
            <p className="error-note" role="alert" style={{ position: "fixed", bottom: 8, left: 8, right: 8 }}>
              {error}
            </p>
          )}
        </>
      )}
      {screen === "confirm" && card && (
        <ConfirmScreen
          dayLabel={card.dayLabel}
          timeLabel={card.timeText}
          task={card.task}
          busy={busy}
          onYes={() => void submit("हो")}
          onNo={() => void submit("नाही")}
          onReplay={() => turn && speak(turn.reply, lang)}
        />
      )}
      {screen === "medicine" && shownDose && (
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
          onTaken={() => void medicineTaken(shownDose)}
          onSnooze={() => void medicineSnooze(shownDose)}
          onOk={toHome}
        />
      )}
      {screen === "saved" && <DoneScreen title="आठवण ठेवली!" line={savedLine} onOk={toHome} />}
      {screen === "reply" && turn && (
        <ReplyScreen
          reply={turn.reply}
          ask={turn.awaiting ? (pending ? "yesno" : "speak") : "none"}
          busy={busy}
          onYes={() => void submit("हो")}
          onNo={() => void submit("नाही")}
          onSpeak={beginListening}
          onOk={toHome}
          onReplay={() => speak(turn.reply, lang)}
        />
      )}
      {screen === "story" && turn && (
        <KahaniScreen
          prompt={turn.reply}
          noteTitle={weekday(now)}
          transcript={heard}
          hint="ऐकतोय… सावकाश सांगा"
          share={
            pending?.action_type === "SHARE_STORY" && turn.awaiting
              ? {
                  names: shareNames.map((c) => c.name),
                  initials: shareNames.map((c) => Array.from(c.name)[0] ?? ""),
                  busy,
                  onYes: () => void submit("हो"),
                  onNo: () => void submit("नाही"),
                }
              : undefined
          }
          onSpeak={beginListening}
          onBack={toHome}
        />
      )}
    </div>
  );
}
