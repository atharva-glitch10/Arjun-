import { Bell, Calendar, Check, ClipboardList, Clock, Image as ImageIcon, ListChecks, Lock, Mic, Phone, Pill, TriangleAlert, Utensils, Volume2 } from "lucide-react";
import type { ReactNode } from "react";

import type { DoseCheck, HealthProfile } from "@/api";

import { Orb } from "@/components/Orb";
import type { OrbState } from "@/components/orbState";

/** Presentational elder screens ("listens with care" design). No fetching and no hard-coded user data: all props. */

export const AI_DISCLOSURE = "अर्जुन — तुमचा AI सोबती";

export interface UpcomingItem {
  key: string;
  when: string;
  what: string;
  /** First letter(s) of a family member, when the item is about a known contact. */
  initials?: string;
  kind: "call" | "reminder" | "appointment";
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
  medicine?: { when: string; name: string };
  busy?: boolean;
  error?: string;
  onSpeak: () => void;
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
            <span className="sub" aria-label={`आत्ता ${p.clock}`}>
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
          {p.items.map((it) => (
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
              <h2>औषधं</h2>
            </div>
            {p.medicine ? (
              <div className="section-row">
                <div>
                  <span className="what">{p.medicine.name}</span>
                  <span className="when">{p.medicine.when}</span>
                </div>
                <span className="status-chip">पुढे</span>
              </div>
            ) : (
              <p className="section-empty">आज आणखी औषध नाही</p>
            )}
          </section>
          <section className="section-card">
            <div className="head">
              <span className="tile">
                <ClipboardList size={24} />
              </span>
              <h2>आजची कामं</h2>
            </div>
            {p.items.length === 0 && <p className="section-empty">आज काही ठरलेलं नाही</p>}
            {p.items.map((it) => (
              <div className="section-row" key={it.key}>
                <div>
                  <span className="what">{it.what}</span>
                  <span className="when">{it.when}</span>
                </div>
                <span className="status-chip later">नंतर</span>
              </div>
            ))}
          </section>
        </div>

        <div className="home-speak">
          <button className="speak-orb" onClick={p.onSpeak} disabled={p.busy} aria-label="अर्जुनशी बोला">
            <span className="orb-phone">
              <WarmOrb size="lg" pulse>
                <Mic size={44} />
              </WarmOrb>
            </span>
            <span className="orb-laptop">
              <div className="lap-rings">
                <div className="lap-mid">
                  <Orb state="idle" label="अर्जुन" size="8.75rem" />
                </div>
              </div>
            </span>
            <span className="label">दाबा आणि बोला</span>
          </button>
        </div>
      </div>

      {p.error && (
        <p className="error-note" role="alert">
          {p.error}
        </p>
      )}

      <div className="btn-row actions">
        <button className="btn secondary" onClick={p.onToday}>
          <ListChecks size={24} aria-hidden />
          आज काय?
        </button>
        <button className="btn help" onClick={p.onHelp}>
          <Phone size={24} aria-hidden />
          मदत
        </button>
      </div>
      {p.onInfo && (
        <button className="btn outline-white" onClick={p.onInfo}>
          <ClipboardList size={24} aria-hidden />
          माझी औषधं आणि माहिती
        </button>
      )}
      <span className="hint-chip">बोला — “भजन लाव”, “राहुलला कॉल कर”, “आज काय आहे?”</span>
      <p className="disclosure">{AI_DISCLOSURE}</p>
    </div>
  );
}

export function ListenScreen(p: {
  heard: string;
  /** Only for the design gallery: in the live app Arjun decides when the sentence is finished. */
  onDone?: () => void;
  onStop: () => void;
  /** Typed fallback (dev / gallery). */
  onType?: { value: string; set: (v: string) => void; send: () => void };
}) {
  const state: OrbState = "listening";
  return (
    <div className="screen listen">
      <div className="heading">
        <h1 className="h1">मी ऐकतोय…</h1>
      </div>
      <div className="orb-wrap" data-orb={state}>
        <WarmOrb size="lg" pulse label="अर्जुन ऐकत आहे" />
        <span className="orb-caption">अर्जुन ऐकतोय…</span>
      </div>
      <div className="said-card" aria-live="polite">
        <span className="t-muted" style={{ fontSize: 16 }}>
          तुम्ही म्हणालात
        </span>
        <p className="quote">{p.heard ? `“${p.heard}”` : "…"}</p>
      </div>
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
            aria-label="येथे लिहा"
            placeholder="येथे लिहा"
          />
          <button className="fbtn" type="submit">
            पाठवा
          </button>
        </form>
      )}
      <div className="stack-end">
        {p.onDone && (
          <button className="btn amber" onClick={p.onDone} disabled={!p.heard.trim()}>
            झालं, पुढे
          </button>
        )}
        <button className="btn outline-white" onClick={p.onStop}>
          थांबा
        </button>
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
      <h1 className="h1">मी असं समजलो</h1>
      <div className="panel">
        <div className="tag-line">
          <span className="tag">{p.dayLabel}</span>
        </div>
        <span className="big-time">{p.timeLabel}</span>
        <span style={{ fontSize: 26, lineHeight: 1.4, fontWeight: 600 }}>{p.task}</span>
      </div>
      <p className="h2" style={{ textAlign: "center" }}>
        बरोबर आहे का?
      </p>
      <div className="stack-end">
        <button className="btn primary big" onClick={p.onYes} disabled={p.busy}>
          <Check size={30} aria-hidden />
          हो, बरोबर
        </button>
        <button className="btn secondary" onClick={p.onNo} disabled={p.busy}>
          नाही, परत सांगते
        </button>
      </div>
      <p className="foot">“हो” किंवा “नाही” बोलूनही चालेल</p>
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
        {p.okLabel ?? "ठीक आहे"}
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
}) {
  return (
    <div className="screen">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <WarmOrb size="md" />
        <h1 className="h2">अर्जुन</h1>
      </div>
      <div className="panel" aria-live="polite">
        <p style={{ fontSize: 27, lineHeight: 1.5, fontWeight: 600 }}>{p.reply}</p>
      </div>
      <div className="stack-end">
        {p.ask === "yesno" && (
          <>
            <button className="btn primary big" onClick={p.onYes} disabled={p.busy}>
              <Check size={30} aria-hidden />
              हो
            </button>
            <button className="btn secondary" onClick={p.onNo} disabled={p.busy}>
              नाही
            </button>
            <p className="foot">“हो” किंवा “नाही” बोलूनही चालेल</p>
          </>
        )}
        {p.ask === "speak" && (
          <button className="btn primary big" onClick={p.onSpeak}>
            <Mic size={30} aria-hidden />
            बोला
          </button>
        )}
        {p.ask === "none" && (
          <button className="btn primary big" onClick={p.onOk}>
            ठीक आहे
          </button>
        )}
      </div>
      <p className="foot">{AI_DISCLOSURE}</p>
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
    return <DoneScreen title="छान, आजी!" line={p.nextLine ?? ""} onOk={p.onOk} />;
  }
  if (p.status === "snoozed") {
    return (
      <div className="screen centered">
        <div className="center-block">
          <div className="badge-done amber pop">
            <Clock size={72} aria-hidden />
          </div>
          <h1 className="h1">ठीक आहे</h1>
          <p className="lead">{p.snoozeUntil ? `${p.snoozeUntil} ला परत सांगतो` : "१५ मिनिटांनी परत सांगतो"}</p>
        </div>
        <button className="btn primary big" onClick={p.onOk}>
          ठीक आहे
        </button>
      </div>
    );
  }
  return (
    <div className="screen">
      <div className="topline">
        <span className="who">आजी</span>
        <span className="sub">{p.timeLabel}</span>
      </div>
      <div className="panel">
        <div className="tag-line">
          <span className="tag">औषधाची वेळ</span>
        </div>
        {p.photoUrl && (
          <div className="photo-slot" role="img" aria-label="औषधाच्या पाकिटाचा फोटो">
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
            घेतली
          </button>
          <button className="btn secondary big" onClick={p.onSnooze} style={{ fontSize: 20 }}>
            १५ मिनिटांनी
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
          हे फक्त स्क्रीनवर आहे, अर्जुनने आवाजात सांगितलं नाही
        </p>
      )}
      <div className="stack-end" style={{ alignItems: "center" }}>
        <p className="speech-note">औषधाबद्दल प्रश्न? डॉक्टरांना विचारा</p>
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
}

const AVATAR_COLORS = ["#e8833a", "#1c6b35", "#13204a"];

export function KahaniScreen(p: KahaniProps) {
  return (
    <div className="screen kahani">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <WarmOrb size="md" />
        <h1 className="h2">आजीची वही</h1>
      </div>
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
            <p style={{ fontSize: 22, lineHeight: 1.4, fontWeight: 700 }}>{p.share.names.join(" आणि ")}ला पाठवू?</p>
          </div>
          <div className="btn-row">
            <button className="btn primary" onClick={p.share.onYes} disabled={p.share.busy}>
              हो, पाठवा
            </button>
            <button className="btn secondary" onClick={p.share.onNo} disabled={p.share.busy}>
              नको
            </button>
          </div>
          <div className="t-muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Lock size={18} aria-hidden />
            <span style={{ fontSize: 16, lineHeight: 1.4 }}>“हो” म्हणेपर्यंत फक्त तुमच्यासाठी</span>
          </div>
        </div>
      ) : (
        <div className="stack-end">
          {p.onSpeak && (
            <button className="btn primary big" onClick={p.onSpeak}>
              <Mic size={28} aria-hidden />
              बोला
            </button>
          )}
          <button className="btn outline-white" onClick={p.onBack}>
            मागे
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
        <h1 className="h1">अर्जुन तयार होतोय…</h1>
      </div>
      <div className="orb-wrap">
        <WarmOrb size="lg" pulse label="अर्जुन तयार होत आहे" />
        <p className="lead" aria-live="polite">
          थोडं थांबा
        </p>
      </div>
      <div className="stack-end">
        <button className="btn outline-white" onClick={p.onStop}>
          थांबा
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
        बोला
      </button>
      <button className="btn secondary" onClick={p.onStop}>
        मागे
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
        मदत
      </h1>
      <p className="alert-text" aria-live="assertive">
        {p.text}
      </p>
      <div className="stack-end">
        <a className="btn help big" href="tel:112" style={{ fontWeight: 700 }}>
          <Phone size={28} aria-hidden />
          112 ला फोन करा
        </a>
        <button className="btn ghost-white" onClick={p.onOk}>
          ठीक आहे
        </button>
      </div>
      <p className="foot">{AI_DISCLOSURE}</p>
    </div>
  );
}

/* ---- Start tap, delivered reminder, touch to hear ----------------------------------------------- */
/** The one-time tap on a fresh page. Browsers allow sound only after a tap, so Arjun cannot speak a reminder before it. */
export function StartScreen(p: { onStart: () => void }) {
  return (
    <div className="screen centered">
      <div className="center-block">
        <WarmOrb size="lg" pulse label="अर्जुन" />
        <h1 className="h1">अर्जुन</h1>
        <p className="lead">आठवणी आणि औषधं सांगण्यासाठी एकदा दाबा</p>
      </div>
      <button className="btn primary big" onClick={p.onStart}>
        <Volume2 size={30} aria-hidden />
        सुरू करा
      </button>
      <p className="foot">{AI_DISCLOSURE}</p>
    </div>
  );
}

/** A reminder that came due. Stays until the elder taps OK. `spoken` false = Arjun did NOT say it; the screen says so. */
export function ReminderCardScreen(p: { task: string; timeLabel: string; spoken: boolean; late: boolean; onOk: () => void }) {
  return (
    <div className="screen">
      <div className="topline">
        <span className="who">आजी</span>
        <span className="sub">{p.late ? `${p.timeLabel} ची आठवण` : p.timeLabel}</span>
      </div>
      <div className="panel" aria-live="polite">
        <div className="tag-line">
          <span className="tag">आठवण</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div className="icon-tile">
            <Bell size={32} />
          </div>
          <p style={{ fontSize: 30, lineHeight: 1.35, fontWeight: 700 }}>{p.task}</p>
        </div>
        <button className="btn primary big" onClick={p.onOk}>
          <Check size={28} aria-hidden />
          ठीक आहे
        </button>
      </div>
      {!p.spoken && (
        <p className="foot" role="note">
          हे फक्त स्क्रीनवर आहे, अर्जुनने आवाजात सांगितलं नाही
        </p>
      )}
      <p className="foot">{AI_DISCLOSURE}</p>
    </div>
  );
}

/** The browser is blocking Arjun's voice: one big tap lets it through. */
export function TouchToHearScreen(p: { onTouch: () => void }) {
  return (
    <div className="screen centered">
      <div className="center-block">
        <h1 className="h1" style={{ lineHeight: 1.4 }}>
          अर्जुनचा आवाज ऐकण्यासाठी दाबा
        </h1>
      </div>
      <button className="btn primary big" onClick={p.onTouch}>
        <Volume2 size={30} aria-hidden />
        ऐका
      </button>
    </div>
  );
}

/* ---- "My medicines and information": what the family wrote, word for word ---------------------------- */
const DOSE_CHIP: Record<DoseCheck["timing"], string> = {
  on_time: "घेतली",
  late: "घेतली",
  pending: "आता / पुढे",
  overdue: "अजून नाही",
  not_confirmed: "अजून नाही",
  said_no: "नाही घेतली",
};

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
      <h1 className="h1">माझी माहिती</h1>
      {p.failed && (
        <p className="error-note" role="alert">
          माहिती आत्ता मिळाली नाही.
        </p>
      )}
      <section className="panel">
        <div className="tag-line">
          <span className="tag">आजची औषधं</span>
        </div>
        {p.doses.length === 0 && <p className="section-empty">आज औषध ठरलेलं नाही</p>}
        {p.doses.map((d) => (
          <div className="section-row" key={d.dose_id}>
            <div>
              {/* Name, dose and instructions exactly as the family entered them (boundary 6). */}
              <span className="what">
                {d.due_at.slice(11, 16)} · {d.name}
              </span>
              <span className="when">{[d.dose, d.instructions].filter(Boolean).join(" · ")}</span>
            </div>
            <span className={`status-chip${d.timing === "on_time" || d.timing === "late" ? " ok" : ""}`}>{DOSE_CHIP[d.timing]}</span>
          </div>
        ))}
      </section>
      <section className="panel">
        <div className="tag-line">
          <span className="tag">घरच्यांनी लिहिलेली माहिती</span>
        </div>
        {pr && !pr.allergies.length && !pr.doctor_name && !pr.conditions.length && !pr.blood_group && !pr.prescription_notes && (
          <p className="section-empty">अजून काही लिहिलेलं नाही</p>
        )}
        {pr && row("अ‍ॅलर्जी", pr.allergies.join(", "))}
        {pr && row("आजार", pr.conditions.join(", "))}
        {pr && row("रक्तगट", pr.blood_group)}
        {pr && row("डॉक्टर", [pr.doctor_name, pr.doctor_contact].filter(Boolean).join(" · "))}
        {pr && row("डॉक्टरांच्या सूचना", pr.prescription_notes)}
      </section>
      <p className="foot">ही माहिती तुमच्या घरच्यांनी लिहिली आहे. औषधाबद्दल प्रश्न? डॉक्टरांना विचारा.</p>
      <div className="stack-end">
        <button className="btn primary big" onClick={p.onBack}>
          ठीक आहे
        </button>
      </div>
    </div>
  );
}
