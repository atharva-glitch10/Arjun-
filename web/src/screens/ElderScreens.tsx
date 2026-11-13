import { Bell, Calendar, Check, ClipboardList, Clock, Image as ImageIcon, ListChecks, Lock, Mic, Phone, Pill, TriangleAlert, Utensils, Volume2 } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import type { DoseCheck, HealthProfile } from "@/api";

import { Orb } from "@/components/Orb";
import type { OrbState } from "@/components/orbState";
import { t } from "@/elder/strings";

import { ChatMessages } from "./ChatScreen";
import type { ChatMsg } from "./ChatScreen";
import type { StringKey } from "@/elder/strings";

/** Presentational elder screens ("listens with care" design). No fetching and no hard-coded user data: all props. */


/** What she calls her companion (family-set in Settings; blank = अर्जुन). Set by ElderApp after it loads the user. */
/** The language tag of the line Arjun is saying (set by ElderApp from the same reply), so the text carries lang=. */
let replyLangTag = "";
export function setReplyLang(lang: string | undefined): void {
  replyLangTag = (lang ?? "").trim();
}

let companionLabel = "अर्जुन";
export const getCompanionLabel = (): string => companionLabel;
export function setCompanionLabel(name: string | undefined): void {
  const n = (name ?? "").trim();
  companionLabel = !n || n.toLowerCase() === "arjun" ? "अर्जुन" : n;
}

const aiDisclosure = (): string => t("ai_disclosure", { name: companionLabel });

export interface UpcomingItem {
  key: string;
  when: string;
  what: string;
  /** First letter(s) of a family member, when the item is about a known contact. */
  initials?: string;
  kind: "call" | "reminder" | "appointment";
  /** When it is due (ms), so the medicine card can sit in time order among these. */
  at?: number;
}

/** The white-core orb used on the warm phone screens. */
function WarmOrb({ size, pulse, label, children }: { size: "lg" | "md"; pulse?: boolean; label?: string; children?: ReactNode }) {
  return (
    <div className={`orb-rings ${size}${pulse ? " orb-pulse" : ""}`} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <div className="orb-mid">
        <div className="orb-core">{children}</div>
      </div>
    </div>
  );
}

function UpcomingCard({ item }: { item: UpcomingItem }) {
  return (
    <div className="upcoming pop">
      {item.initials ? (
        <div className="avatar" role="img" aria-label={item.what}>
          {item.initials}
        </div>
      ) : (
        <div className="avatar soft">{item.kind === "appointment" ? <Calendar size={26} /> : <Bell size={26} />}</div>
      )}
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span className="when">{item.when}</span>
        <span className="what">{item.what}</span>
      </div>
    </div>
  );
}

export interface HomeProps {
  evening: boolean;
  greeting: string;
  dateLine: string;
  /** Current time, e.g. "सकाळी ९:१५" - always visible so the elder can orient through the day. */
  clock?: string;
  /** Name of the display language, e.g. "मराठी". */
  languageLabel?: string;
  items: UpcomingItem[];
  /** Next medicine card. Only passed when a medicine API exists. */
  medicine?: { when: string; name: string; at?: number };
  busy?: boolean;
  error?: string;
  onSpeak: () => void;
  /** /chat already has its own record button, so the big orb is hidden there. */
  hideSpeak?: boolean;
  onToday: () => void;
  onHelp: () => void;
  /** Opens the family-written information screen. */
  onInfo?: () => void;
}

export function HomeScreen(p: HomeProps) {
  return (
    <div className="screen home">
      {/* phone header */}
      <div className="topline topline-p">
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="who">{p.dateLine}</span>
          {p.clock && (
            <span className="sub" aria-label={t("now_at", { t: p.clock ?? "" })}>
              {p.clock}
            </span>
          )}
        </div>
        {p.languageLabel && <span className="lang-chip">{p.languageLabel}</span>}
      </div>
      {/* laptop header */}
      <div className="topline-l">
        <div className="greeting">
          <h1 className="h1">{p.greeting}!</h1>
          <span className="sub">{[p.dateLine, p.clock].filter(Boolean).join(" · ")}</span>
        </div>
        {p.languageLabel && <span className="lang-chip">{p.languageLabel}</span>}
      </div>

      <div className="home-main">
        <div className="greeting topline-p-greeting phone-only">
          <h1 className="h1">{p.greeting}!</h1>
        </div>

        {/* phone: the next things as cards */}
        <div className="home-cards">
          {/* in time order: a 7 pm call is shown before the 8:30 pm tablet (live run 2026-11-09, origin #26) */}
          {p.items
            .filter((it) => !p.medicine || p.medicine.at === undefined || (it.at ?? 0) <= p.medicine.at)
            .map((it) => (
              <UpcomingCard key={it.key} item={it} />
            ))}
          {p.medicine && (
            <div className="upcoming">
              <div className="avatar soft" style={{ background: "var(--ok-bg)", color: "var(--ok-fg)" }}>
                <Pill size={26} />
              </div>
              <div style={{ display: "flex", flexDirection: "column" }}>
                <span className="when">{p.medicine.when}</span>
                <span className="what">{p.medicine.name}</span>
              </div>
            </div>
          )}
          {p.items
            .filter((it) => p.medicine && p.medicine.at !== undefined && (it.at ?? 0) > p.medicine.at)
            .map((it) => (
              <UpcomingCard key={it.key} item={it} />
            ))}
        </div>

        {/* laptop: the same data as two sections */}
        <div className="home-sections">
          <section className="section-card">
            <div className="head">
              <span className="tile">
                <Pill size={24} />
              </span>
              <h2>{t("meds")}</h2>
            </div>
            {p.medicine ? (
              <div className="section-row">
                <div>
                  <span className="what">{p.medicine.name}</span>
                  <span className="when">{p.medicine.when}</span>
                </div>
                <span className="status-chip">{t("next_chip")}</span>
              </div>
            ) : (
              <p className="section-empty">{t("no_more_med")}</p>
            )}
          </section>
          <section className="section-card">
            <div className="head">
              <span className="tile">
                <ClipboardList size={24} />
              </span>
              <h2>{t("todays_tasks")}</h2>
            </div>
            {p.items.length === 0 && <p className="section-empty">{t("nothing_planned")}</p>}
            {p.items.map((it) => (
              <div className="section-row" key={it.key}>
                <div>
                  <span className="what">{it.what}</span>
                  <span className="when">{it.when}</span>
                </div>
                <span className="status-chip later">{t("later_chip")}</span>
              </div>
            ))}
          </section>
        </div>

        {!p.hideSpeak && (
        <div className="home-speak">
          <button className="speak-orb" onClick={p.onSpeak} disabled={p.busy} aria-label={t("talk_to", { name: companionLabel })}>
            <span className="orb-phone">
              <WarmOrb size="lg" pulse>
                <Mic size={44} />
              </WarmOrb>
            </span>
            <span className="orb-laptop">
              <div className="lap-rings">
                <div className="lap-mid">
                  <Orb state="idle" label={companionLabel} size="8.75rem" />
                </div>
              </div>
            </span>
            <span className="label">{t("tap_and_speak")}</span>
          </button>
        </div>
        )}
      </div>

      {p.error && (
        <p className="error-note" role="alert">
          {p.error}
        </p>
      )}

      <div className="btn-row actions">
        <button className="btn secondary" onClick={p.onToday}>
          <ListChecks size={24} aria-hidden />
          {t("whats_today")}
        </button>
        <button className="btn help" onClick={p.onHelp}>
          <Phone size={24} aria-hidden />
          {t("help")}
        </button>
      </div>
      {p.onInfo && (
        <button className="btn outline-white" onClick={p.onInfo}>
          <ClipboardList size={24} aria-hidden />
          {t("my_info_btn")}
        </button>
      )}
      <span className="hint-chip">{t("hint_chip")}</span>
      <p className="disclosure">{aiDisclosure()}</p>
    </div>
  );
}

/* ---- Conversation: shadcn message scroller + bubbles (ChatScreen.tsx) ---------------------------------------------- */
export type { ChatMsg } from "./ChatScreen";

/** The conversation so far for the elder screens that still carry a thread (hands-free / dashboard preview). /chat uses ChatScreen. */
export function ChatThread(p: { messages: ChatMsg[]; live?: string; typing?: boolean }) {
  return (
    <div className="ui-root flex h-[45vh] min-h-[220px] w-full">
      <ChatMessages
        messages={p.messages}
        live={p.live}
        status={p.typing ? "thinking" : "idle"}
        statusLabel={p.typing ? t("thinking") : ""}
        emptyText={`${t("you_said")} …`}
      />
    </div>
  );
}

export function ListenScreen(p: {
  heard: string;
  /** Only for the design gallery: in the live app Arjun decides when the sentence is finished. */
  onDone?: () => void;
  hideStop?: boolean;
  onStop: () => void;
  /** Typed fallback (dev / gallery). */
  onType?: { value: string; set: (v: string) => void; send: () => void };
  /** The conversation so far, shown WhatsApp-style instead of the single "you said" card. */
  thread?: ChatMsg[];
}) {
  const state: OrbState = "listening";
  return (
    <div className="screen listen">
      <div className="heading">
        <h1 className="h1">{t("listening_h")}</h1>
      </div>
      <div className="orb-wrap" data-orb={state}>
        <WarmOrb size="lg" pulse label={t("listening_aria", { name: companionLabel })} />
        <span className="orb-caption">{t("listening_cap", { name: companionLabel })}</span>
      </div>
      {p.thread ? (
        <ChatThread messages={p.thread} live={p.heard} />
      ) : (
        <div className="said-card" aria-live="polite">
          <span className="t-muted" style={{ fontSize: 16 }}>
            {t("you_said")}
          </span>
          <p className="quote">{p.heard ? `“${p.heard}”` : "…"}</p>
        </div>
      )}
      {p.onType && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            p.onType?.send();
          }}
          style={{ display: "flex", gap: 8 }}
        >
          <input
            className="fam-input"
            style={{ flex: 1, fontSize: 20 }}
            value={p.onType.value}
            onChange={(e) => p.onType?.set(e.target.value)}
            aria-label={t("type_here")}
            placeholder={t("type_here")}
          />
          <button className="fbtn" type="submit">
            {t("send")}
          </button>
        </form>
      )}
      <div className="stack-end">
        {p.onDone && (
          <button className="btn amber" onClick={p.onDone} disabled={!p.heard.trim()}>
            {t("done_next")}
          </button>
        )}
        {!p.hideStop && <button className="btn outline-white" onClick={p.onStop}>
          {t("stop")}
        </button>}
      </div>
    </div>
  );
}

export interface ConfirmProps {
  dayLabel: string;
  timeLabel: string;
  task: string;
  busy?: boolean;
  onYes: () => void;
  onNo: () => void;
}

export function ConfirmScreen(p: ConfirmProps) {
  return (
    <div className="screen">
      <h1 className="h1">{t("understood")}</h1>
      <div className="panel">
        <div className="tag-line">
          <span className="tag">{p.dayLabel}</span>
        </div>
        <span className="big-time">{p.timeLabel}</span>
        <span style={{ fontSize: 26, lineHeight: 1.4, fontWeight: 600 }}>{p.task}</span>
      </div>
      <p className="h2" style={{ textAlign: "center" }}>
        {t("correct_q")}
      </p>
      <div className="stack-end">
        <button className="btn primary big" onClick={p.onYes} disabled={p.busy}>
          <Check size={30} aria-hidden />
          {t("yes_correct")}
        </button>
        <button className="btn secondary" onClick={p.onNo} disabled={p.busy}>
          {t("no_again")}
        </button>
      </div>
      <p className="foot">{t("say_yes_no")}</p>
    </div>
  );
}

/** Success screens: reminder saved, medicine taken. */
export function DoneScreen(p: { title: string; line: string; onOk: () => void; okLabel?: string }) {
  return (
    <div className="screen centered">
      <div className="center-block">
        <div className="badge-done pop" aria-hidden="true">
          <Check size={80} strokeWidth={2.6} />
        </div>
        <h1 className="h1">{p.title}</h1>
        <p className="lead">{p.line}</p>
      </div>
      <button className="btn primary big" onClick={p.onOk}>
        {p.okLabel ?? t("ok")}
      </button>
    </div>
  );
}

/** Arjun's spoken reply shown as text, with yes/no when a spoken yes is needed. One decision only. */
export function ReplyScreen(p: {
  reply: string;
  ask: "yesno" | "speak" | "none";
  busy?: boolean;
  onYes: () => void;
  onNo: () => void;
  onSpeak: () => void;
  onOk: () => void;
  hideOk?: boolean;
  thread?: ChatMsg[];
}) {
  return (
    <div className="screen">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <WarmOrb size="md" />
        <h1 className="h2">{companionLabel}</h1>
      </div>
      {p.thread && p.thread.length > 0 ? (
        <ChatThread messages={p.thread} />
      ) : (
        <div className="panel" aria-live="polite">
          <p lang={replyLangTag || undefined} style={{ fontSize: 27, lineHeight: 1.5, fontWeight: 600 }}>
            {p.reply}
          </p>
        </div>
      )}
      <div className="stack-end">
        {p.ask === "yesno" && (
          <>
            <button className="btn primary big" onClick={p.onYes} disabled={p.busy}>
              <Check size={30} aria-hidden />
              {t("yes")}
            </button>
            <button className="btn secondary" onClick={p.onNo} disabled={p.busy}>
              {t("no")}
            </button>
            <p className="foot">{t("say_yes_no")}</p>
          </>
        )}
        {p.ask === "speak" && (
          <button className="btn primary big" onClick={p.onSpeak}>
            <Mic size={30} aria-hidden />
            {t("speak")}
          </button>
        )}
        {p.ask === "none" && !p.hideOk && (
          <button className="btn primary big" onClick={p.onOk}>
            {t("ok")}
          </button>
        )}
      </div>
      <p className="foot">{aiDisclosure()}</p>
    </div>
  );
}

/* ---- Medicine time ------------------------------------------------------------------------- */
export interface MedicineProps {
  status: "due" | "taken" | "snoozed";
  timeLabel: string;
  /** Name and dose are rendered verbatim as the family entered them (read from SQL). */
  name: string;
  dose: string;
  mealNote?: string;
  photoUrl?: string;
  nextLine?: string;
  snoozeUntil?: string;
  /** True until T8: the prompt is only on the screen, Arjun did not say it (CLAUDE.md boundary 14). */
  notSpoken?: boolean;
  onTaken: () => void;
  onSnooze: () => void;
  onOk: () => void;
}

export function MedicineScreen(p: MedicineProps) {
  if (p.status === "taken") {
    return <DoneScreen title={t("well_done")} line={p.nextLine ?? ""} onOk={p.onOk} />;
  }
  if (p.status === "snoozed") {
    return (
      <div className="screen centered">
        <div className="center-block">
          <div className="badge-done amber pop">
            <Clock size={72} aria-hidden />
          </div>
          <h1 className="h1">{t("ok")}</h1>
          <p className="lead">{p.snoozeUntil ? t("ok_remind_after", { t: p.snoozeUntil }) : t("remind_in_15")}</p>
        </div>
        <button className="btn primary big" onClick={p.onOk}>
          {t("ok")}
        </button>
      </div>
    );
  }
  return (
    <div className="screen">
      <div className="topline">
        <span className="who">{t("who")}</span>
        <span className="sub">{p.timeLabel}</span>
      </div>
      <div className="panel">
        <div className="tag-line">
          <span className="tag">{t("med_time")}</span>
        </div>
        {p.photoUrl && (
          <div className="photo-slot" role="img" aria-label={t("med_photo")}>
            <img src={p.photoUrl} alt="" />
          </div>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div className="icon-tile">{p.photoUrl ? <ImageIcon size={30} /> : <Pill size={34} />}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
            {/* Name and dose exactly as the family entered them (boundary 6). */}
            <span style={{ fontSize: 26, fontWeight: 700, lineHeight: 1.2 }}>{p.name}</span>
            <span style={{ fontSize: 18, fontWeight: 500, color: "var(--ink-muted)" }}>{p.dose}</span>
          </div>
        </div>
        <div className="btn-row">
          <button className="btn primary big" onClick={p.onTaken}>
            <Check size={26} aria-hidden />
            {t("dose_taken")}
          </button>
          <button className="btn secondary big" onClick={p.onSnooze} style={{ fontSize: 20 }}>
            {t("in_15")}
          </button>
        </div>
      </div>
      {p.mealNote && (
        <div className="pill-line">
          <Utensils size={22} aria-hidden />
          <span>{p.mealNote}</span>
        </div>
      )}
      {p.notSpoken && (
        <p className="foot" role="note">
          {t("screen_only")}
        </p>
      )}
      <div className="stack-end" style={{ alignItems: "center" }}>
        <p className="speech-note">{t("med_ask_doctor")}</p>
      </div>
    </div>
  );
}

/* ---- Story notebook: "आजीची वही" ------------------------------------------------------------- */
export interface KahaniProps {
  prompt: string;
  noteTitle: string;
  transcript: string;
  hint: string;
  share?: { names: string[]; initials: string[]; busy?: boolean; onYes: () => void; onNo: () => void };
  onSpeak?: () => void;
  onBack: () => void;
  thread?: ChatMsg[];
}

const AVATAR_COLORS = ["#e8833a", "#1c6b35", "#13204a"];

export function KahaniScreen(p: KahaniProps) {
  return (
    <div className="screen kahani">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <WarmOrb size="md" />
        <h1 className="h2">{t("book_h")}</h1>
      </div>
      {p.thread && p.thread.length > 0 ? (
        <ChatThread messages={p.thread} />
      ) : (
        <>
          <div className="arjun-chip">
            <p>{p.prompt}</p>
          </div>
          <div className="note-page" aria-live="polite">
            <span className="title">{p.noteTitle}</span>
            <p className="text">{p.transcript}</p>
            <span className="t-muted" style={{ fontSize: 16 }}>
              {p.hint}
            </span>
          </div>
        </>
      )}
      {p.share ? (
        <div className="share-card">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ display: "flex" }}>
              {p.share.initials.slice(0, 3).map((ini, i) => (
                <div
                  key={`${ini}${i}`}
                  className="avatar small"
                  style={{ background: AVATAR_COLORS[i % AVATAR_COLORS.length], marginLeft: i === 0 ? 0 : -14 }}
                  role="img"
                  aria-label={p.share?.names[i] ?? ""}
                >
                  {ini}
                </div>
              ))}
            </div>
            <p style={{ fontSize: 22, lineHeight: 1.4, fontWeight: 700 }}>{t("send_to", { names: p.share.names.join(t("and")) })}</p>
          </div>
          <div className="btn-row">
            <button className="btn primary" onClick={p.share.onYes} disabled={p.share.busy}>
              {t("yes_send")}
            </button>
            <button className="btn secondary" onClick={p.share.onNo} disabled={p.share.busy}>
              {t("nako")}
            </button>
          </div>
          <div className="t-muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Lock size={18} aria-hidden />
            <span style={{ fontSize: 16, lineHeight: 1.4 }}>{t("only_you")}</span>
          </div>
        </div>
      ) : (
        <div className="stack-end">
          {p.onSpeak && (
            <button className="btn primary big" onClick={p.onSpeak}>
              <Mic size={28} aria-hidden />
              {t("speak")}
            </button>
          )}
          <button className="btn outline-white" onClick={p.onBack}>
            {t("back")}
          </button>
        </div>
      )}
    </div>
  );
}

/* ---- Voice session states ---------------------------------------------------------------------- */
/** Joining the room / waiting for the agent. Plain words, never a blank screen. */
export function ConnectingScreen(p: { onStop: () => void }) {
  return (
    <div className="screen listen">
      <div className="heading">
        <h1 className="h1">{t("getting_ready")}</h1>
      </div>
      <div className="orb-wrap">
        <WarmOrb size="lg" pulse label={t("getting_ready")} />
        <p className="lead" aria-live="polite">
          {t("please_wait")}
        </p>
      </div>
      <div className="stack-end">
        <button className="btn outline-white" onClick={p.onStop}>
          {t("stop")}
        </button>
      </div>
    </div>
  );
}

/** The connection failed or dropped: say so plainly and offer one big retry. */
export function FailedScreen(p: { message: string; onRetry: () => void; onStop: () => void }) {
  return (
    <div className="screen centered">
      <div className="center-block">
        <h1 className="h1" style={{ lineHeight: 1.4 }} role="alert">
          {p.message}
        </h1>
      </div>
      <button className="btn primary big" onClick={p.onRetry}>
        <Mic size={30} aria-hidden />
        {t("speak")}
      </button>
      <button className="btn secondary" onClick={p.onStop}>
        {t("back")}
      </button>
    </div>
  );
}

/** Emergency / distress: the fixed template, shown the moment Arjun says it, whatever else is on screen. */
export function SafetyScreen(p: { text: string; onOk: () => void }) {
  return (
    <div className="screen safety">
      <div className="alert-icon" aria-hidden>
        <TriangleAlert size={56} />
      </div>
      <h1 className="h1" style={{ textAlign: "center" }}>
        {t("help")}
      </h1>
      <p className="alert-text" aria-live="assertive">
        {p.text}
      </p>
      <div className="stack-end">
        <a className="btn help big" href="tel:112" style={{ fontWeight: 700 }}>
          <Phone size={28} aria-hidden />
          {t("call_112")}
        </a>
        <button className="btn ghost-white" onClick={p.onOk}>
          {t("ok")}
        </button>
      </div>
      <p className="foot">{aiDisclosure()}</p>
    </div>
  );
}

/* ---- Start tap, delivered reminder, touch to hear ----------------------------------------------- */
/** The one-time tap on a fresh page. Browsers allow sound only after a tap, so Arjun cannot speak a reminder before it. */
export function StartScreen(p: { onStart: () => void; hideStart?: boolean }) {
  return (
    <div className="screen centered">
      <div className="center-block">
        <WarmOrb size="lg" pulse label={companionLabel} />
        <h1 className="h1">{t("start_hello", { name: companionLabel })}</h1>
        <p className="lead">{t("lets_chat")}</p>
      </div>
      {!p.hideStart && <button className="btn primary big" onClick={p.onStart}>
        <Volume2 size={30} aria-hidden />
        {t("start_btn")}
      </button>}
      <p className="foot">{aiDisclosure()}</p>
    </div>
  );
}

/** A reminder that came due. Stays until the elder taps OK. `spoken` false = Arjun did NOT say it; the screen says so. */
export function ReminderCardScreen(p: { task: string; timeLabel: string; spoken: boolean; late: boolean; onOk: () => void }) {
  return (
    <div className="screen">
      <div className="topline">
        <span className="who">{t("who")}</span>
        <span className="sub">{p.late ? t("reminder_late", { t: p.timeLabel }) : p.timeLabel}</span>
      </div>
      <div className="panel" aria-live="polite">
        <div className="tag-line">
          <span className="tag">{t("reminder_tag")}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div className="icon-tile">
            <Bell size={32} />
          </div>
          <p style={{ fontSize: 30, lineHeight: 1.35, fontWeight: 700 }}>{p.task}</p>
        </div>
        <button className="btn primary big" onClick={p.onOk}>
          <Check size={28} aria-hidden />
          {t("ok")}
        </button>
      </div>
      {!p.spoken && (
        <p className="foot" role="note">
          {t("screen_only")}
        </p>
      )}
      <p className="foot">{aiDisclosure()}</p>
    </div>
  );
}

/** The browser is blocking Arjun's voice: one big tap lets it through. */
export function TouchToHearScreen(p: { onTouch: () => void }) {
  return (
    <div className="screen centered">
      <div className="center-block">
        <h1 className="h1" style={{ lineHeight: 1.4 }}>
          {t("tap_to_hear")}
        </h1>
      </div>
      <button className="btn primary big" onClick={p.onTouch}>
        <Volume2 size={30} aria-hidden />
        {t("listen")}
      </button>
    </div>
  );
}

/* ---- "My medicines and information": what the family wrote, word for word ---------------------------- */
const DOSE_CHIP_KEY = {
  on_time: "dose_taken", late: "dose_taken", pending: "dose_pending", overdue: "dose_not_yet",
  not_confirmed: "dose_not_yet", said_no: "dose_said_no",
} as const satisfies Record<DoseCheck["timing"], StringKey>;
const doseChip = (timing: DoseCheck["timing"]): string => t(DOSE_CHIP_KEY[timing]);

export function MyInfoScreen(p: { profile: HealthProfile | null; doses: DoseCheck[]; failed?: boolean; onBack: () => void }) {
  const pr = p.profile;
  const row = (label: string, value: string) =>
    value ? (
      <div className="section-row">
        <div>
          <span className="when">{label}</span>
          <span className="what">{value}</span>
        </div>
      </div>
    ) : null;
  return (
    <div className="screen">
      <h1 className="h1">{t("info_h")}</h1>
      {p.failed && (
        <p className="error-note" role="alert">
          {t("info_unavailable")}
        </p>
      )}
      <section className="panel">
        <div className="tag-line">
          <span className="tag">{t("todays_meds")}</span>
        </div>
        {p.doses.length === 0 && <p className="section-empty">{t("no_med_today")}</p>}
        {p.doses.map((d) => (
          <div className="section-row" key={d.dose_id}>
            <div>
              {/* Name, dose and instructions exactly as the family entered them (boundary 6). */}
              <span className="what">
                {d.due_at.slice(11, 16)} · {d.name}
              </span>
              <span className="when">{[d.dose, d.instructions].filter(Boolean).join(" · ")}</span>
            </div>
            <span className={`status-chip${d.timing === "on_time" || d.timing === "late" ? " ok" : ""}`}>{doseChip(d.timing)}</span>
          </div>
        ))}
      </section>
      <section className="panel">
        <div className="tag-line">
          <span className="tag">{t("family_wrote")}</span>
        </div>
        {pr && !pr.allergies.length && !pr.doctor_name && !pr.conditions.length && !pr.blood_group && !pr.prescription_notes && (
          <p className="section-empty">{t("nothing_written")}</p>
        )}
        {pr && row(t("allergies"), pr.allergies.join(", "))}
        {pr && row(t("conditions"), pr.conditions.join(", "))}
        {pr && row(t("blood_group"), pr.blood_group)}
        {pr && row(t("doctor"), [pr.doctor_name, pr.doctor_contact].filter(Boolean).join(" · "))}
        {pr && row(t("doctor_notes"), pr.prescription_notes)}
      </section>
      <p className="foot">{t("info_foot")}</p>
      <div className="stack-end">
        <button className="btn primary big" onClick={p.onBack}>
          {t("ok")}
        </button>
      </div>
    </div>
  );
}
