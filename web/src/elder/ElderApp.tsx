import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { Contact, Delivery, DoseCheck, DueNow, Dose, HealthProfile, PendingAction } from "../api";
import {
  ConfirmScreen,
  ConnectingScreen,
  DoneScreen,
  FailedScreen,
  HomeScreen,
  KahaniScreen,
  ListenScreen,
  MedicineScreen,
  MyInfoScreen,
  ReminderCardScreen,
  ReplyScreen,
  SafetyScreen,
  StartScreen,
  TouchToHearScreen,
  setCompanionLabel,
  setReplyLang,
} from "../screens/ElderScreens";
import type { ChatMsg, UpcomingItem } from "../screens/ElderScreens";
import { failureText, shownFor } from "../voice/state";
import { REST_AFTER_MS, cardFor, restingScreen, shouldAutoStart, shouldConnectHandsFree } from "./cards";
import { useArjunVoice } from "../voice/useArjunVoice";
import { LinkPrompt, MediaScreen } from "./MediaScreen";
import { VideoCallScreen } from "./VideoCallScreen";
import { elderLanguage, elderText, timeGreeting } from "./i18n";
import { LANGUAGE_NAMES, setElderLang, t as tr, uiLanguage } from "./strings";
import type { ElderLang } from "./strings";
import { useAppActions } from "./useAppActions";
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

// How the elder is addressed in headings: the family's "what should Arjun call her" (Settings), else "आजी".
const defaultAddress = (lang: ElderLang): string => tr("who", undefined, lang);

const hhmmOf = (iso: string): string => iso.slice(11, 16);

// Tap-to-talk is the default (owner decision 2026-11-08): the mic stays closed until the elder taps बोला.
// `?handsfree=1` brings back the always-listening mode (for a dedicated, always-open elder device).
const HANDS_FREE = (() => {
  try {
    return new URLSearchParams(window.location.search).get("handsfree") === "1";
  } catch {
    return false;
  }
})();

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
  const [displayLanguage, setDisplayLanguage] = useState("mr");
  setElderLang(displayLanguage);
  const [addressAs, setAddressAs] = useState(defaultAddress("mr"));
  // Whose voice Arjun may chat in (a family-approved cloned voice); shown so she always knows. Re-checked each minute.
  const [clonedName, setClonedName] = useState<string | null>(null);
  useEffect(() => {
    const check = () =>
      void api
        .voiceLabel(userId)
        .then((v) => setClonedName(v.name))
        .catch(() => setClonedName(null));
    check();
    const id = window.setInterval(check, 60_000);
    return () => window.clearInterval(id);
  }, [userId]);
  const [error, setError] = useState("");
  const [due, setDue] = useState<DueNow>({ current: [], next: null });
  const [medState, setMedState] = useState<"due" | "taken" | "snoozed">("due");
  const [medicineOpen, setMedicineOpen] = useState(false);
  // "My medicines and information": what the family wrote, word for word. Opened by the elder, closed by her.
  const [infoOpen, setInfoOpen] = useState(false);
  const [info, setInfo] = useState<{ profile: HealthProfile | null; doses: DoseCheck[]; failed: boolean }>({
    profile: null,
    doses: [],
    failed: false,
  });
  const openInfo = () => {
    setInfoOpen(true);
    void Promise.allSettled([api.healthProfile(userId), api.medicineCheck(userId)]).then(([pr, ds]) =>
      setInfo({
        profile: pr.status === "fulfilled" ? pr.value : null,
        doses: ds.status === "fulfilled" ? ds.value : [],
        failed: pr.status === "rejected" || ds.status === "rejected",
      }),
    );
  };
  const lastDose = useRef<Dose | null>(null);
  const lastCard = useRef<ReturnType<typeof pendingToCard> | null>(null);
  const queuedText = useRef<string | null>(null);

  // T8: delivered reminders / medicines. The SQL list is the truth; the card stays until it is acknowledged there.
  const [armed, setArmed] = useState(false); // the one-time Start tap on this page load
  const [open, setOpen] = useState<Delivery[]>([]);
  const [queued, setQueued] = useState(0);
  // After "घेतली" / "१५ मिनिटांनी सांग" on a delivered medicine the SQL card is gone; this keeps the answer screen up.
  const [cardDone, setCardDone] = useState<{
    status: "taken" | "snoozed";
    time: string;
    name: string;
    dose: string;
  } | null>(null);
  const lastAutoStart = useRef<number | null>(null);

  const voice = useArjunVoice(userId);
  const uiLang = uiLanguage(voice.activeLang, displayLanguage); // a spoken switch changes the labels too, not only the reply
  setElderLang(uiLang);
  setReplyLang(voice.replyLang || uiLang);
  useEffect(() => {
    document.documentElement.lang = voice.replyLang || uiLang; // fonts and screen readers follow the text's language
  }, [voice.replyLang, uiLang]);
  // The conversation as a WhatsApp-style thread (team notes 2026-11-10): each finished reply adds her last sentence
  // and Arjun's answer. Kept for this visit only; nothing is stored.
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const lastHeard = useRef("");
  const chatId = useRef(0);
  useEffect(() => {
    if (voice.heard.trim()) lastHeard.current = voice.heard.trim();
  }, [voice.heard]);
  useEffect(() => {
    const reply = (voice.reply ?? "").trim();
    if (!reply) return;
    const at = new Date();
    const time = `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
    setChat((c) => {
      const add: ChatMsg[] = [];
      const said = lastHeard.current;
      const last = c[c.length - 1];
      if (said && !(last && last.who === "me" && last.text === said)) add.push({ id: ++chatId.current, who: "me", text: said, time });
      if (!(last && last.who === "arjun" && last.text === reply)) add.push({ id: ++chatId.current, who: "arjun", text: reply, time });
      lastHeard.current = "";
      return add.length ? [...c, ...add].slice(-40) : c;
    });
  }, [voice.reply]);
  const deliveredCard = cardFor(open, voice.item);
  const snapshot = { ...voice.snapshot, armed: armed || HANDS_FREE, hasCard: deliveredCard !== undefined };
  const [restedTurn, setRestedTurn] = useState(0);
  const shown = restingScreen(shownFor(snapshot), voice.snapshot.turn, restedTurn, HANDS_FREE);
  const { phase } = voice.snapshot;
  // Apps by voice: a video, WhatsApp or a family link opens on this page (agent attribute "arjun.action").
  const apps = useAppActions(voice, userId, contacts, shown === "safety", () => {
    if (voice.snapshot.phase !== "live") void voice.start();
  });

  // Hands-free: open the voice session as the page opens and keep it open; reconnect by itself after a drop.
  const attempts = useRef({ last: null as number | null, count: 0 });
  useEffect(() => {
    if (!HANDS_FREE) return;
    if (phase === "live") {
      attempts.current.count = 0;
      return;
    }
    const tryNow = () => {
      const a = attempts.current;
      const since = a.last === null ? null : Date.now() - a.last;
      if (shouldConnectHandsFree({ handsFree: true, phase, sinceLastMs: since, attempt: a.count })) {
        a.last = Date.now();
        if (phase === "failed") a.count += 1;
        void voice.arm().then(() => voice.start());
      }
    };
    tryNow();
    const id = window.setInterval(tryNow, 1_000);
    return () => window.clearInterval(id);
  }, [phase, voice]);

  // Hands-free: a reply screen goes back to the home screen by itself (no OK tap); a new reply shows again.
  useEffect(() => {
    if (!HANDS_FREE) return;
    const s = shownFor(snapshot);
    if (s !== "reply" && s !== "saved" && s !== "story") return;
    const turn = voice.snapshot.turn;
    const id = window.setTimeout(() => setRestedTurn(turn), REST_AFTER_MS[s]);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voice.snapshot.turn, voice.snapshot.screen, voice.snapshot.phase]);

  const loadDeliveries = useCallback(async () => {
    try {
      const all = await api.openDeliveries(userId);
      setOpen(all);
      setQueued(all.filter((d) => d.status === "queued").length);
    } catch {
      // keep what is on screen; the next poll tries again
    }
  }, [userId]);

  useEffect(() => {
    void loadDeliveries();
    const id = window.setInterval(() => void loadDeliveries(), 5_000);
    const onFocus = () => void loadDeliveries();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [loadDeliveries]);

  // The agent just spoke a delivery: read the card from SQL now instead of waiting for the next poll.
  useEffect(() => {
    if (voice.item) void loadDeliveries();
  }, [voice.item, voice.snapshot.turn, loadDeliveries]);

  // Pre-warm: join a quiet room as the page opens so the first tap (or the first reminder) is fast.
  const prewarm = voice.prewarm;
  useEffect(() => {
    void prewarm();
  }, [prewarm]);

  // A reminder is waiting and no session is open: after the Start tap the page opens one by itself.
  useEffect(() => {
    const since = lastAutoStart.current === null ? null : Date.now() - lastAutoStart.current;
    if (shouldAutoStart({ armed, phase, queued, sinceLastMs: since })) {
      lastAutoStart.current = Date.now();
      void voice.start();
    }
  }, [armed, phase, queued, voice]);

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
      const [reminders, appt, people, user] = await Promise.all([
        api.reminders(userId),
        api.nextAppointment(userId),
        api.contacts(userId),
        api.getUser(userId),
      ]);
      const lang = elderLanguage(user.preferred_languages?.[0] || user.language);
      setElderLang(lang); // before any time/day text below is built
      setDisplayLanguage(lang);
      setAddressAs(user.address_as?.trim() || defaultAddress(lang));
      setCompanionLabel(user.speech_style?.companion_name);
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
            at: at.getTime(),
            when: day === dayWord(t, t) ? spokenTime(hhmm) : `${day} ${spokenTime(hhmm)}`,
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
            at: at.getTime(),
            when: day === dayWord(t, t) ? spokenTime(hhmm) : `${day} ${spokenTime(hhmm)}`,
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

  // A dose that core-api no longer has open (404 gone, 409 already taken/missed/no snoozes left) must not trap her on
  // the medicine screen: close it and refresh. Any other failure stays on screen WITH a visible message.
  const medicineFailed = (e: unknown) => {
    const code = e instanceof Error ? Number(e.message.slice(0, 3)) : 0;
    if (code === 404 || code === 409) {
      setMedicineOpen(false);
      lastDose.current = null;
      void pollMedicines();
      return;
    }
    setError(tr("err_retry"));
  };

  const medicineTaken = async (d: Dose) => {
    try {
      await api.doseTaken(userId, d.id);
      setMedState("taken");
      void pollMedicines();
    } catch (e) {
      medicineFailed(e);
    }
  };

  const medicineSnooze = async (d: Dose) => {
    try {
      await api.doseSnooze(userId, d.id);
      setMedState("snoozed");
      void pollMedicines();
    } catch (e) {
      medicineFailed(e);
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
    if (phase === "live") {  // hands-free: the session is already open, just say it
      if (text) void voice.sendText(text);
      return;
    }
    queuedText.current = text ?? null;
    void voice.start();
  };

  const toHome = () => {
    if (HANDS_FREE) {
      setRestedTurn(voice.snapshot.turn); // back to the home screen; the session keeps listening
    } else {
      voice.stop();
    }
    queuedText.current = null;
    lastCard.current = null;
    setPending(null);
    setMedicineOpen(false);
    setError("");
    void pollMedicines();
    void loadHome();
  };

  const ackReminder = async (d: Delivery) => {
    try {
      await api.ackDelivery(userId, d.id, "ok");
      await loadDeliveries();
    } catch (e) {
      await cardFailed(d, e);
    }
  };

  // A card whose item core-api no longer has open (404 gone; 409 dose already taken/missed, no snoozes left, e.g.
  // last night's dose still shown) must not trap her: mark the CARD seen (outcome "closed", never "taken") and move on.
  // Any other failure keeps the card and shows a visible message.
  const cardFailed = async (d: Delivery, e: unknown) => {
    const code = e instanceof Error ? Number(e.message.slice(0, 3)) : 0;
    if (code === 404 || code === 409) {
      try {
        await api.ackDelivery(userId, d.id, "closed");
      } catch {
        // already acknowledged or gone: reloading below is enough
      }
      setError("");
      void loadDeliveries();
      void pollMedicines();
      return;
    }
    setError(tr("err_retry"));
  };

  const answerMedicineCard = async (d: Delivery, status: "taken" | "snoozed") => {
    try {
      // core-api acknowledges the delivery itself when the dose is marked (self-reported) or snoozed
      if (status === "taken") await api.doseTaken(userId, d.ref_id);
      else await api.doseSnooze(userId, d.ref_id);
      setCardDone({ status, time: timeLabel(hhmmOf(d.due_at)), name: d.label, dose: d.detail });
      void loadDeliveries();
      void pollMedicines();
    } catch (e) {
      await cardFailed(d, e);
    }
  };

  const fetchAlternates = useCallback((q: string) => api.youtubeSearch(userId, q), [userId]);
  const yes = () => void voice.sendText(tr("yes"));
  const no = () => void voice.sendText(tr("no"));

  const evening = forceEvening ?? isEvening(now);
  const shownDose = dueDose ?? lastDose.current;
  // The familiar-voice chip only where Arjun may actually chat in that voice: never on medicine, safety or confirm.
  // Emergency screen: share the device's location ONCE for this emergency. core-api keeps it only if a physical
  // emergency was just recorded (emotional distress: discarded) and sends the family a map link. Never tracked.
  const sharedLocation = useRef(false);
  useEffect(() => {
    if (shown !== "safety") {
      sharedLocation.current = false;
      return;
    }
    if (sharedLocation.current || !("geolocation" in navigator)) return;
    sharedLocation.current = true;
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        void api
          .emergencyLocation(userId, {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            accuracy_m: Math.round(pos.coords.accuracy || 0),
          })
          .catch(() => undefined),
      () => undefined, // refused / unavailable: the family alert and calls still happen without it
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 30_000 },
    );
  }, [shown, userId]);

  const chipScreen =
    ["listen", "reply", "story"].includes(shown as string) || (shown === "home" && !(medicineOpen && shownDose));
  if (dueDose) lastDose.current = dueDose;
  const card = pending?.action_type === "CREATE_REMINDER" ? pendingToCard(pending, now) : null;
  const shareNames = contacts.slice(0, 3);
  const tapOpen = phase === "live";

  const NOT_HOME = ["start", "touch", "card", "connecting", "failed", "safety", "listen", "confirm", "saved", "story", "reply"];
  const isHome =
    !infoOpen && !NOT_HOME.includes(shown as string) && !(cardDone && shown === "home") && !(medicineOpen && shownDose);

  const body = () => {
    if (infoOpen && shown === "home" && !(medicineOpen && shownDose))
      return <MyInfoScreen profile={info.profile} doses={info.doses} failed={info.failed} onBack={() => setInfoOpen(false)} />;
    if (cardDone && (shown === "home" || shown === "card"))
      return (
        <MedicineScreen
          status={cardDone.status}
          timeLabel={cardDone.time}
          name={cardDone.name}
          dose={cardDone.dose}
          nextLine={due.next ? tr("next_med_at", { t: timeLabel(hhmmOf(due.next.due_at)) }) : tr("no_more_med")}
          onTaken={() => undefined}
          onSnooze={() => undefined}
          onOk={() => setCardDone(null)}
        />
      );
    switch (shown) {
      case "start":
        return (
          <StartScreen
            onStart={() => {
              setArmed(true);
              void voice.arm();
            }}
          />
        );
      case "touch":
        return <TouchToHearScreen onTouch={() => void voice.unlockAudio()} />;
      case "card": {
        if (!deliveredCard) return <ListenScreen heard={voice.heard} onStop={toHome} thread={chat} />;
        const dl = deliveredCard.delivery;
        if (dl.kind === "medicine") {
          const dose = due.current.find((x) => x.id === dl.ref_id);
          return (
            <MedicineScreen
              status="due"
              timeLabel={timeLabel(hhmmOf(dl.due_at))}
              name={dl.label}
              dose={dl.detail}
              mealNote={dose && (dose.anchor === "lunch" || dose.anchor === "dinner") ? tr("meal_done_q") : undefined}
              photoUrl={dose?.photo_url || undefined}
              nextLine={due.next ? tr("next_med_at", { t: timeLabel(hhmmOf(due.next.due_at)) }) : tr("no_more_med")}
              notSpoken={!deliveredCard.spoken}
              onTaken={() => void answerMedicineCard(dl, "taken")}
              onSnooze={() => void answerMedicineCard(dl, "snoozed")}
              onOk={() => void loadDeliveries()}
            />
          );
        }
        return (
          <ReminderCardScreen
            task={dl.label}
            timeLabel={timeLabel(hhmmOf(dl.due_at))}
            spoken={deliveredCard.spoken}
            late={dl.late}
            onOk={() => void ackReminder(dl)}
          />
        );
      }
      case "connecting":
        return <ConnectingScreen onStop={toHome} />;
      case "failed":
        return (
          <FailedScreen
            message={failureText(voice.snapshot.failure ?? "dropped")}
            onRetry={() => begin()}
            onStop={toHome}
          />
        );
      case "safety":
        return <SafetyScreen text={voice.reply} onOk={voice.dismissSafety} />;
      case "listen":
        return <ListenScreen heard={voice.heard} onStop={toHome} thread={chat} />;
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
              thread={chat}
              noteTitle={weekday(now)}
              transcript={voice.heard}
              hint={tr("hint_listen_slow")}
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
            thread={chat}
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
            title={tr("saved_reminder")}
            line={c ? `${dayWord(c.when, now)} ${periodOfDay(c.when.getHours())} ${tr("remind_you")}` : voice.reply}
            onOk={toHome}
          />
        );
      }
      case "story":
        return (
          <KahaniScreen
            prompt={voice.reply}
              thread={chat}
            noteTitle={weekday(now)}
            transcript={voice.heard}
            hint={tr("hint_listen_slow")}
            onSpeak={() => void voice.start()}
            onBack={toHome}
          />
        );
      case "reply":
        return (
          <ReplyScreen
            reply={voice.reply}
            thread={chat}
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
                shownDose.anchor === "lunch" || shownDose.anchor === "dinner" ? tr("meal_done_q") : undefined
              }
              photoUrl={shownDose.photo_url || undefined}
              nextLine={due.next ? tr("next_med_at", { t: timeLabel(hhmmOf(due.next.due_at)) }) : tr("no_more_med")}
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
            languageLabel={LANGUAGE_NAMES[uiLang]}
            greeting={`${timeGreeting(uiLang, now.getHours())}, ${addressAs}`}
            dateLine={evening ? `${weekday(now)} · ${periodOfDay(now.getHours())}` : dateLine(now)}
            clock={timeLabel(`${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`)}
            items={items}
            medicine={
              due.next
                ? {
                    when: `${periodOfDay(Number(hhmmOf(due.next.due_at).slice(0, 2)))} · ${timeLabel(hhmmOf(due.next.due_at)).split(" ")[1]}`,
                    name: due.next.name,
                    at: parseNaive(due.next.due_at).getTime(),
                  }
                : undefined
            }
            error={error}
            onSpeak={() => begin()}
            onToday={() => begin(tr("cmd_today"))}
            onHelp={() => begin(tr("cmd_help"))}
            onInfo={openInfo}
          />
        );
    }
  };

  const live = phase === "live";
  return (
    <div
      className={`elder-shell${shown === "safety" ? " is-safety" : isHome ? " is-home" : ""}`}
    >
      {HANDS_FREE && live && shown === "home" && (
        <div className="hf-badge" role="status">
          <span className="hf-dot" aria-hidden /> {tr("listening_any_time")}
        </div>
      )}
      {(medicineOpen || shown === "card") && error && (
        <div className="med-error" role="alert">
          {error}
        </div>
      )}
      {clonedName && chipScreen && (
        <div className="voice-chip" role="status">
          <span aria-hidden>♥</span> {voiceChipText(displayLanguage, clonedName)}
        </div>
      )}
      {voice.family && (
        <div className="family-call-banner" role="status" aria-live="polite">
          <span className="family-call-dot" aria-hidden />
          {tr("family_speaking", { name: voice.family })}
        </div>
      )}
      {live && voice.thinking && (
        <div className="thinking-marker" role="status" aria-live="polite">
          <span className="dots" aria-hidden>
            <i />
            <i />
            <i />
          </span>
          {tr("thinking")}
        </div>
      )}
      {body()}
      {(apps.videoCall || apps.videoCallStarting) && (
        <VideoCallScreen
          call={apps.videoCall}
          starting={apps.videoCallStarting}
          room={voice.room}
          userId={userId}
          onEnd={() => void apps.finishVideoCall()}
          onMissed={apps.missedVideoCall}
        />
      )}
      {apps.media && shown !== "safety" && (
        <MediaScreen
          key={apps.media.turn}
          action={apps.media}
          control={apps.control}
          onReport={apps.reportMedia}
          onClosed={apps.onMediaClosed}
          ducked={voice.mediaDuck}
          fetchAlternates={fetchAlternates}
        />
      )}
      {apps.blocked && shown !== "safety" && (
        <LinkPrompt title={apps.blocked.title} onOpen={apps.openBlocked} onCancel={apps.cancelBlocked} />
      )}
      {apps.link && shown !== "safety" && (
        <div className="link-bar" role="status">
          <span>{tr("opened", { title: apps.link.title })}</span>
          <button type="button" className="media-btn" onClick={apps.closeLink}>
            ◀ {tr("back_small")}
          </button>
        </div>
      )}
      {HANDS_FREE && (
        <label className="volume" title={tr("volume")}>
          <span aria-hidden>🔈</span>
          <input
            type="range"
            min={0.1}
            max={1}
            step={0.05}
            value={voice.volume}
            aria-label={tr("volume")}
            onChange={(e) => voice.setVolume(Number(e.target.value))}
          />
          <span aria-hidden>🔊</span>
        </label>
      )}
    </div>
  );
}

function voiceChipText(language: string, name: string): string {
  if (language === "hi") return `${name} की आवाज़ में बात`;
  if (language === "mr") return `${name}च्या आवाजात गप्पा`;
  return `Talking in ${name}'s voice`;
}
