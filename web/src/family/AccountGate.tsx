import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../api";
import type { AccountMe } from "../api";

type Phase = { kind: "checking" } | { kind: "off" } | { kind: "login" } | { kind: "in"; me: AccountMe };

/**
 * Family login (team notes 2026-11-10: "login and authentication so that we can create multiple users").
 * Only when core-api runs with ARJUN_AUTH=1; otherwise /auth/me answers 404 and the dashboard opens as before.
 * After login the family sees ONLY the elders their account belongs to, can add another elder, and log out.
 * The first account ever created owns the elders that already exist (the seeded demo household).
 */
export function AccountGate(p: { userId: number; onUser: (id: number) => void; children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>({ kind: "checking" });
  const { onUser, userId } = p;

  const load = useCallback(async () => {
    try {
      const me = await api.authMe();
      setPhase({ kind: "in", me });
      const first = me.elders[0];
      if (first && !me.elders.some((e) => e.id === userId)) onUser(first.id);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      setPhase(msg.startsWith("404") ? { kind: "off" } : { kind: "login" });
    }
  }, [onUser, userId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (phase.kind === "checking") return <div className="family" style={{ minHeight: "60vh" }} />;
  if (phase.kind === "off") return <>{p.children}</>;
  if (phase.kind === "login") return <LoginPage onIn={() => void load()} />;

  const { me } = phase;
  return (
    <>
      <div className="acct-bar" role="navigation" aria-label="Account">
        <span className="acct-who">{me.account.name}</span>
        <label className="acct-pick">
          Elder
          <select value={userId} onChange={(e) => onUser(Number(e.target.value))}>
            {me.elders.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        <AddElder
          onAdd={async (name, lang) => {
            const made = await api.addElder(name, lang);
            await load();
            onUser(made.id);
          }}
        />
        <button
          className="fbtn"
          onClick={async () => {
            await api.logout().catch(() => undefined);
            setPhase({ kind: "login" });
          }}
        >
          Log out
        </button>
      </div>
      {me.elders.length ? (
        p.children
      ) : (
        <div className="acct-card">
          <h2>Add the person you care for</h2>
          <p>Use "Add elder" above. You can add more than one.</p>
        </div>
      )}
    </>
  );
}

function AddElder(p: { onAdd: (name: string, lang: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [lang, setLang] = useState("mr");
  const [err, setErr] = useState("");
  if (!open)
    return (
      <button className="fbtn" onClick={() => setOpen(true)}>
        + Add elder
      </button>
    );
  return (
    <form
      className="acct-add"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await p.onAdd(name.trim(), lang);
          setOpen(false);
          setName("");
        } catch (x) {
          setErr(x instanceof Error ? x.message : "Could not add");
        }
      }}
    >
      <input className="fam-input" aria-label="Elder's name" placeholder="Name (e.g. हीराबाई)" value={name} onChange={(e) => setName(e.target.value)} />
      <select className="fam-input" aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value)}>
        <option value="mr">मराठी</option>
        <option value="hi">हिंदी</option>
        <option value="en">English</option>
        <option value="ta">தமிழ்</option>
        <option value="kn">ಕನ್ನಡ</option>
        <option value="te">తెలుగు</option>
        <option value="gu">ગુજરાતી</option>
        <option value="bn">বাংলা</option>
        <option value="pa">ਪੰਜਾਬੀ</option>
        <option value="ml">മലയാളം</option>
      </select>
      <button className="fbtn solid" type="submit" disabled={!name.trim()}>
        Add
      </button>
      <button className="fbtn" type="button" onClick={() => setOpen(false)}>
        Cancel
      </button>
      {err && <span className="acct-err">{err}</span>}
    </form>
  );
}

function LoginPage(p: { onIn: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setErr("");
    setBusy(true);
    try {
      if (mode === "signup") await api.signup(name.trim(), email.trim(), password);
      else await api.login(email.trim(), password);
      p.onIn();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      setErr(
        msg.startsWith("401") || msg.startsWith("429")
          ? "Wrong email or password."
          : msg.startsWith("409")
            ? "An account with this email already exists. Log in instead."
            : msg.startsWith("422")
              ? "Check the email, and use a password of at least 10 characters."
              : "Could not reach Arjun. Is it running?",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="acct-page">
      <form
        className="acct-card"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <h1>Arjun · Family</h1>
        <p className="acct-sub">{mode === "login" ? "Log in to see how your loved one is doing." : "Create a family account."}</p>
        {mode === "signup" && (
          <label>
            Your name
            <input className="fam-input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}
        <label>
          Email
          <input className="fam-input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password {mode === "signup" && <span className="acct-hint">(at least 10 characters)</span>}
          <input
            className="fam-input"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {err && (
          <p className="acct-err" role="alert">
            {err}
          </p>
        )}
        <button className="fbtn solid" type="submit" disabled={busy || !email || !password || (mode === "signup" && !name.trim())}>
          {mode === "login" ? "Log in" : "Create account"}
        </button>
        <button type="button" className="acct-link" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
          {mode === "login" ? "New here? Create an account" : "Already have an account? Log in"}
        </button>
      </form>
    </div>
  );
}
