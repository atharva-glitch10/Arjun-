import {
  BellIcon,
  CalendarIcon,
  CheckIcon,
  ClockIcon,
  Diya,
  HeartPulseIcon,
  ImageIcon,
  ListIcon,
  LockIcon,
  MicIcon,
  MoonIcon,
  PhoneIcon,
  PillIcon,
  SunriseIcon,
  ThaliIcon,
  Toran,
} from "./Motifs";

/** Presentational Ghar screens. No fetching and no hard-coded user data: everything arrives as props. */

export const AI_DISCLOSURE = "अर्जुन — तुमचा AI सोबती";

export interface UpcomingItem {
  key: string;
  when: string;
  what: string;
  /** First letter(s) of a family member, when the item is about a known contact. */
  initials?: string;
  kind: "call" | "reminder" | "appointment";
}

function UpcomingCard({ item }: { item: UpcomingItem }) {
  const icon =
    item.initials ? (
      <div className="avatar" role="img" aria-label={item.what}>
        {item.initials}
      </div>
    ) : (
      <div className="avatar soft">{item.kind === "appointment" ? <CalendarIcon /> : <BellIcon size={34} />}</div>
    );
  return (
    <div className="card-row pop">
      {icon}
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
  items: UpcomingItem[];
  /** Next medicine card (evening design). Only passed when a medicine API exists. */
  medicine?: { when: string; name: string };
  busy?: boolean;
  error?: string;
  onSpeak: () => void;
  onToday: () => void;
  onHelp: () => void;
}

export function HomeScreen(p: HomeProps) {
  return (
    <div className={`screen${p.evening ? " night" : ""}`} style={p.evening ? undefined : { padding: 0 }}>
      {!p.evening && <Toran />}
      <div
        style={{
          flexGrow: 1,
          display: "flex",
          flexDirection: "column",
          gap: 18,
          padding: p.evening ? 0 : "8px 22px 24px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <h1 className="h-display" style={{ fontSize: p.evening ? 34 : 36 }}>
              {p.greeting}
            </h1>
            <span className="t-muted" style={{ fontSize: 22, lineHeight: 1.4 }}>
              {p.dateLine}
            </span>
            {p.clock && (
              <span aria-label={`आत्ता ${p.clock}`} style={{ fontSize: 34, lineHeight: 1.25, fontWeight: 800 }}>
                {p.clock}
              </span>
            )}
          </div>
          {p.evening ? <MoonIcon /> : <SunriseIcon />}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {p.medicine && (
            <div className="card-row">
              <div className="avatar leaf" style={{ color: "var(--ghar-leaf)" }}>
                <PillIcon />
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

        <div className="center-block" style={{ gap: 22 }}>
          {p.evening ? (
            <button className="speak-diya" onClick={p.onSpeak} disabled={p.busy} aria-label="अर्जुनशी बोला">
              <div className="halo" />
              <div className="core">
                <Diya size={54} flame="var(--ghar-kumkum)" />
                <span>बोला</span>
              </div>
            </button>
          ) : (
            <button className="speak breathe" onClick={p.onSpeak} disabled={p.busy} aria-label="अर्जुनशी बोला">
              <MicIcon />
              <span>बोला</span>
            </button>
          )}
          <span className="t-muted" style={{ fontSize: 22, lineHeight: 1.4 }}>
            {p.evening ? "गप्पा मारूया?" : "दाबा आणि बोला"}
          </span>
        </div>

        {p.error && (
          <p className="error-note" role="alert">
            {p.error}
          </p>
        )}

        <div className="btn-row">
          <button className="btn outline-indigo" onClick={p.onToday}>
            {!p.evening && <ListIcon />}
            आज काय?
          </button>
          <button className="btn help" onClick={p.onHelp}>
            {!p.evening && <PhoneIcon />}
            मदत
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
          {!p.evening && <Diya size={26} />}
          <span className="t-muted" style={{ fontSize: 18, lineHeight: 1.4 }}>
            {AI_DISCLOSURE}
          </span>
        </div>
      </div>
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
  return (
    <div className="screen listen">
      <h1 className="h-display" style={{ fontSize: 38, textAlign: "center" }}>
        मी ऐकतोय…
      </h1>
      <div style={{ height: 250, position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div
          className="halo"
          style={{
            position: "absolute",
            width: 230,
            height: 230,
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(242,182,50,.55) 0%, rgba(242,182,50,0) 70%)",
          }}
        />
        <div style={{ position: "relative" }}>
          <Diya size={150} detailed label="अर्जुन ऐकत आहे" />
        </div>
      </div>
      <div className="said-card" aria-live="polite">
        <span className="t-muted" style={{ fontSize: 20, lineHeight: 1.4 }}>
          तुम्ही म्हणालात
        </span>
        <p style={{ fontSize: 28, lineHeight: 1.5, fontWeight: 600, minHeight: 42 }}>
          {p.heard ? `“${p.heard}”` : "…"}
        </p>
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
          <button className="btn haldi" onClick={p.onDone} disabled={!p.heard.trim()}>
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
    <div className="screen" style={{ paddingTop: 48, paddingBottom: 26, gap: 20 }}>
      <h1 className="h-display" style={{ fontSize: 34 }}>
        मी असं समजलो
      </h1>
      <div className="big-card">
        <div className="band">{p.dayLabel}</div>
        <div className="body">
          <span className="key-value">{p.timeLabel}</span>
          <span style={{ fontSize: 28, lineHeight: 1.4, fontWeight: 600 }}>{p.task}</span>
        </div>
      </div>
      <p className="h-display" style={{ fontSize: 32, textAlign: "center" }}>
        बरोबर आहे का?
      </p>
      <div className="stack-end">
        <button className="btn primary" style={{ minHeight: 92, fontSize: 30 }} onClick={p.onYes} disabled={p.busy}>
          <CheckIcon />
          हो, बरोबर
        </button>
        <button className="btn secondary" style={{ minHeight: 84, fontSize: 26 }} onClick={p.onNo} disabled={p.busy}>
          नाही, परत सांगते
        </button>
      </div>
      <p className="footnote">“हो” किंवा “नाही” बोलूनही चालेल</p>
    </div>
  );
}

/** Success screens: reminder saved, medicine taken, reading recorded. */
export function DoneScreen(p: { title: string; line: string; onOk: () => void; okLabel?: string }) {
  return (
    <div className="screen centered-end" style={{ gap: 22 }}>
      <div className="center-block">
        <div className="success-badge pop" aria-hidden="true" style={{ color: "#fff" }}>
          <CheckIcon size={88} w={2.6} />
        </div>
        <h1 className="h-display" style={{ fontSize: 40 }}>
          {p.title}
        </h1>
        <p style={{ fontSize: 26, lineHeight: 1.5 }}>{p.line}</p>
      </div>
      <button className="btn primary" onClick={p.onOk}>
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
    <div className="screen" style={{ gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Diya size={44} />
        <h1 className="h-display" style={{ fontSize: 32 }}>
          अर्जुन
        </h1>
      </div>
      <div className="big-card">
        <div className="body" style={{ padding: "22px 22px 26px" }} aria-live="polite">
          <p style={{ fontSize: 28, lineHeight: 1.5, fontWeight: 600 }}>{p.reply}</p>
        </div>
      </div>
      <div className="stack-end">
        {p.ask === "yesno" && (
          <>
            <button className="btn primary" style={{ minHeight: 92, fontSize: 30 }} onClick={p.onYes} disabled={p.busy}>
              <CheckIcon />
              हो
            </button>
            <button className="btn secondary" onClick={p.onNo} disabled={p.busy}>
              नाही
            </button>
            <p className="footnote">“हो” किंवा “नाही” बोलूनही चालेल</p>
          </>
        )}
        {p.ask === "speak" && (
          <button className="btn primary" onClick={p.onSpeak}>
            <MicIcon size={34} />
            बोला
          </button>
        )}
        {p.ask === "none" && (
          <button className="btn primary" onClick={p.onOk}>
            ठीक आहे
          </button>
        )}
      </div>
      <p className="footnote">{AI_DISCLOSURE}</p>
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
      <div className="screen centered-end">
        <div className="center-block">
          <div className="success-badge haldi pop" style={{ color: "var(--ghar-ink)" }}>
            <ClockIcon />
          </div>
          <h1 className="h-display" style={{ fontSize: 38 }}>
            ठीक आहे
          </h1>
          <p style={{ fontSize: 24, lineHeight: 1.5 }}>{p.snoozeUntil ? `${p.snoozeUntil} ला परत सांगतो` : "१५ मिनिटांनी परत सांगतो"}</p>
        </div>
        <button className="btn primary" onClick={p.onOk}>
          ठीक आहे
        </button>
      </div>
    );
  }
  return (
    <div className="screen" style={{ gap: 18, paddingBottom: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <BellIcon />
        <div style={{ display: "flex", flexDirection: "column" }}>
          <h1 className="h-display" style={{ fontSize: 36, lineHeight: 1.3 }}>
            औषधाची वेळ
          </h1>
          <span className="t-muted" style={{ fontSize: 22, lineHeight: 1.4 }}>
            {p.timeLabel}
          </span>
        </div>
      </div>
      {p.notSpoken && (
        <p className="footnote" role="note" style={{ textAlign: "left" }}>
          हे फक्त स्क्रीनवर आहे, अर्जुनने आवाजात सांगितलं नाही
        </p>
      )}
      {p.mealNote && (
        <div className="pill">
          <ThaliIcon />
          <span>{p.mealNote}</span>
        </div>
      )}
      <div className="big-card">
        <div className="photo-slot" role="img" aria-label="औषधाच्या पाकिटाचा फोटो">
          {p.photoUrl ? (
            <img src={p.photoUrl} alt="" />
          ) : (
            <>
              <ImageIcon />
              <span>औषधाच्या पाकिटाचा फोटो नाही</span>
            </>
          )}
        </div>
        <div className="body" style={{ padding: "16px 22px 20px", gap: 2 }}>
          <span style={{ fontSize: 40, lineHeight: 1.15, fontWeight: 800, color: "var(--ghar-indigo)" }}>{p.name}</span>
          <span style={{ fontSize: 26, lineHeight: 1.4, fontWeight: 600 }}>{p.dose}</span>
        </div>
      </div>
      <div className="stack-end">
        <button className="btn success" onClick={p.onTaken}>
          <CheckIcon />
          घेतली
        </button>
        <button className="btn secondary" onClick={p.onSnooze}>
          १५ मिनिटांनी सांग
        </button>
      </div>
      <p className="footnote">औषधाबद्दल प्रश्न? डॉक्टरांना विचारा</p>
    </div>
  );
}

/* ---- Vitals (BP) --------------------------------------------------------------------------- */
export interface VitalsProps {
  status: "confirm" | "saved";
  timeNote: string;
  said: string;
  /** Parsed by rules, never by the LLM, and only saved after a spoken or tapped yes. */
  bp: string;
  pulse?: string;
  familyName: string;
  onYes: () => void;
  onRetry: () => void;
  onOk: () => void;
}

export function VitalsScreen(p: VitalsProps) {
  if (p.status === "saved") {
    return <DoneScreen title="नोंद केली" line={`डॉक्टरांना दाखवण्यासाठी ${p.familyName}कडे ठेवली`} onOk={p.onOk} />;
  }
  return (
    <div className="screen" style={{ gap: 16, paddingBottom: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div className="avatar" style={{ background: "var(--ghar-surface)", color: "var(--ghar-kumkum)", boxShadow: "0 2px 0 var(--ghar-card-shadow)" }}>
          <HeartPulseIcon />
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <h1 className="h-display" style={{ fontSize: 34, lineHeight: 1.3 }}>
            BP तपासायची वेळ
          </h1>
          <span className="t-muted" style={{ fontSize: 22, lineHeight: 1.4 }}>
            {p.timeNote}
          </span>
        </div>
      </div>
      <div className="said-card white">
        <span className="t-muted" style={{ fontSize: 20, lineHeight: 1.4 }}>
          तुम्ही सांगितलं
        </span>
        <p style={{ fontSize: 24, lineHeight: 1.5, fontWeight: 600 }}>“{p.said}”</p>
      </div>
      <div className="big-card">
        <div className="band indigo">मी असं लिहितोय</div>
        <div style={{ padding: "18px 22px 22px", display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span className="t-muted" style={{ fontSize: 20, lineHeight: 1.4 }}>
              BP
            </span>
            <span className="key-value sm">{p.bp}</span>
          </div>
          {p.pulse && (
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span className="t-muted" style={{ fontSize: 20, lineHeight: 1.4 }}>
                पल्स
              </span>
              <span className="key-value sm">{p.pulse}</span>
            </div>
          )}
        </div>
      </div>
      <p className="h-display" style={{ fontSize: 30, textAlign: "center" }}>
        बरोबर आहे का?
      </p>
      <div className="stack-end">
        <button className="btn primary" onClick={p.onYes}>
          <CheckIcon size={32} />
          हो, बरोबर
        </button>
        <button className="btn secondary" style={{ minHeight: 78 }} onClick={p.onRetry}>
          नाही, परत सांगते
        </button>
      </div>
      <p className="footnote">हे आकडे {p.familyName}लाही दिसतील</p>
    </div>
  );
}

/* ---- Kahani: "आजीची वही" ------------------------------------------------------------------- */
export interface KahaniProps {
  prompt: string;
  noteTitle: string;
  transcript: string;
  hint: string;
  share?: { names: string[]; initials: string[]; busy?: boolean; onYes: () => void; onNo: () => void };
  onSpeak?: () => void;
  onBack: () => void;
}

const AVATAR_COLORS = ["var(--ghar-marigold)", "var(--ghar-leaf)", "var(--ghar-indigo)"];

export function KahaniScreen(p: KahaniProps) {
  return (
    <div className="screen kahani">
      <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#fff" }}>
        <Diya size={36} />
        <h1 className="h-display" style={{ fontSize: 32 }}>
          आजीची वही
        </h1>
      </div>
      <div className="arjun-chip">
        <p>{p.prompt}</p>
      </div>
      <div className="ruled" aria-live="polite">
        <span className="t-muted" style={{ fontSize: 18, fontWeight: 600 }}>
          {p.noteTitle}
        </span>
        <p className="h-display" style={{ fontSize: 25 }}>
          {p.transcript}
        </p>
        <span className="t-muted" style={{ fontSize: 18 }}>
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
            <p style={{ fontSize: 24, lineHeight: 1.4, fontWeight: 800 }}>{p.share.names.join(" आणि ")}ला पाठवू?</p>
          </div>
          <div className="btn-row" style={{ gap: 10 }}>
            <button className="btn primary compact" onClick={p.share.onYes} disabled={p.share.busy}>
              हो, पाठवा
            </button>
            <button className="btn secondary compact" style={{ minHeight: 76 }} onClick={p.share.onNo} disabled={p.share.busy}>
              नको
            </button>
          </div>
          <div className="t-muted" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <LockIcon />
            <span style={{ fontSize: 18, lineHeight: 1.4 }}>“हो” म्हणेपर्यंत फक्त तुमच्यासाठी</span>
          </div>
        </div>
      ) : (
        <div className="stack-end">
          {p.onSpeak && (
            <button className="btn haldi" onClick={p.onSpeak}>
              <MicIcon size={34} />
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


/* ---- Voice session states (T6) ------------------------------------------------------------- */
/** Joining the room / waiting for the agent. Plain words, never a blank screen. */
export function ConnectingScreen(p: { onStop: () => void }) {
  return (
    <div className="screen listen">
      <h1 className="h-display" style={{ fontSize: 38, textAlign: "center" }}>
        अर्जुन तयार होतोय…
      </h1>
      <div className="center-block" style={{ minHeight: 250 }}>
        <Diya size={150} detailed label="अर्जुन तयार होत आहे" />
      </div>
      <p style={{ fontSize: 24, lineHeight: 1.5, textAlign: "center" }} aria-live="polite">
        थोडं थांबा
      </p>
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
    <div className="screen centered-end" style={{ gap: 22 }}>
      <div className="center-block">
        <h1 className="h-display" style={{ fontSize: 38, lineHeight: 1.4 }} role="alert">
          {p.message}
        </h1>
      </div>
      <button className="btn primary" style={{ minHeight: 100, fontSize: 34 }} onClick={p.onRetry}>
        <MicIcon size={38} />
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
    <div className="screen" style={{ gap: 22, paddingTop: 56 }}>
      <h1 className="h-display" style={{ fontSize: 38, color: "var(--ghar-kumkum)" }}>
        मदत
      </h1>
      <div className="big-card" style={{ borderColor: "var(--ghar-kumkum)" }}>
        <div className="body" style={{ padding: "22px 22px 26px" }} aria-live="assertive">
          <p style={{ fontSize: 30, lineHeight: 1.5, fontWeight: 700 }}>{p.text}</p>
        </div>
      </div>
      <div className="stack-end">
        <a className="btn help" href="tel:112" style={{ minHeight: 92, fontSize: 30, textDecoration: "none" }}>
          <PhoneIcon />
          112 ला फोन करा
        </a>
        <button className="btn secondary" onClick={p.onOk}>
          ठीक आहे
        </button>
      </div>
      <p className="footnote">{AI_DISCLOSURE}</p>
    </div>
  );
}
