import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../api";
import type { AccountMe } from "../api";
import { AUTH_LANGS, at, authErrorKey, detectAuthLang, saveAuthLang } from "./authText";
import type { AuthLang } from "./authText";

type Phase = { kind: "checking" } | { kind: "off" } | { kind: "login" } | { kind: "in"; me: AccountMe };

/**
 * Family login (team notes 2026-11-10: "login and authentication so that we can create multiple users").
 * Only when core-api runs with ARJUN_AUTH=1; otherwise /auth/me answers 404 and the dashboard opens as before.
 * After login the family sees ONLY the elders their account belongs to, can add another elder, and log out.
 * Sign-up needs the sign-up code (ARJUN_SIGNUP_CODE). All words: authText.ts (mr / hi / en).
 */
export function AccountGate(p: { userId: number; onUser: (id: number) => void; children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>({ kind: "checking" });
  const [lang, setLangState] = useState<AuthLang>(detectAuthLang);
  const setLang = (l: AuthLang) => {
    saveAuthLang(l);
    setLangState(l);
  };
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
  if (phase.kind === "login") return <LoginPage lang={lang} setLang={setLang} onIn={() => void load()} />;

  const { me } = phase;
  return (
    <>
      <div className="acct-bar" role="navigation" aria-label="Account">
        <span className="acct-who">{me.account.name}</span>
        <label className="acct-pick">
          {at("elder", lang)}
          <select value={userId} onChange={(e) => onUser(Number(e.target.value))}>
            {me.elders.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        <AddElder
          lang={lang}
          onAdd={async (name, elderLang) => {
            const made = await api.addElder(name, elderLang);
            await load();
            onUser(made.id);
          }}
        />
        <LangSwitch lang={lang} setLang={setLang} />
        <button
          className="fbtn"
          onClick={async () => {
            await api.logout().catch(() => undefined);
            setPhase({ kind: "login" });
          }}
        >
          {at("logout", lang)}
        </button>
      </div>
      {me.elders.length ? (
        p.children
      ) : (
        <div className="acct-card">
          <h2>{at("add_title", lang)}</h2>
          <p>{at("add_help", lang)}</p>
        </div>
      )}
    </>
  );
}

function LangSwitch(p: { lang: AuthLang; setLang: (l: AuthLang) => void }) {
  return (
    <span role="group" aria-label="Language" className="acct-lang">
      {AUTH_LANGS.map(([id, label]) => (
        <button key={id} type="button" className="acct-link" aria-pressed={p.lang === id} style={{ fontWeight: p.lang === id ? 800 : 400 }} onClick={() => p.setLang(id)}>
          {label}
        </button>
      ))}
    </span>
  );
}

function AddElder(p: { lang: AuthLang; onAdd: (name: string, lang: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [lang, setLang] = useState("mr");
  const [err, setErr] = useState("");
  if (!open)
    return (
      <button className="fbtn" onClick={() => setOpen(true)}>
        {at("add_elder", p.lang)}
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
          setErr(x instanceof Error ? x.message : at("add_failed", p.lang));
        }
      }}
    >
      <input className="fam-input" aria-label={at("elder_name", p.lang)} placeholder={at("name_ph", p.lang)} value={name} onChange={(e) => setName(e.target.value)} />
      <select className="fam-input" aria-label={at("language", p.lang)} value={lang} onChange={(e) => setLang(e.target.value)}>
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
        {at("add", p.lang)}
      </button>
      <button className="fbtn" type="button" onClick={() => setOpen(false)}>
        {at("cancel", p.lang)}
      </button>
      {err && <span className="acct-err">{err}</span>}
    </form>
  );
}

function LoginPage(p: { lang: AuthLang; setLang: (l: AuthLang) => void; onIn: () => void }) {
  const { lang } = p;
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setErr("");
    setBusy(true);
    try {
      if (mode === "signup") await api.signup(name.trim(), email.trim(), password, code.trim());
      else await api.login(email.trim(), password);
      p.onIn();
    } catch (e) {
      setErr(at(authErrorKey(e instanceof Error ? e.message : "", mode), lang));
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
        <LangSwitch lang={lang} setLang={p.setLang} />
        <h1>{at("title", lang)}</h1>
        <p className="acct-sub">{mode === "login" ? at("login_sub", lang) : at("signup_sub", lang)}</p>
        {mode === "signup" && (
          <label>
            {at("your_name", lang)}
            <input className="fam-input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}
        <label>
          {at("email", lang)}
          <input className="fam-input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          {at("password", lang)} {mode === "signup" && <span className="acct-hint">{at("password_hint", lang)}</span>}
          <input
            className="fam-input"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {mode === "signup" && (
          <label>
            {at("signup_code", lang)} <span className="acct-hint">{at("signup_code_hint", lang)}</span>
            <input className="fam-input" autoComplete="off" value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
        )}
        {err && (
          <p className="acct-err" role="alert">
            {err}
          </p>
        )}
        <button className="fbtn solid" type="submit" disabled={busy || !email || !password || (mode === "signup" && (!name.trim() || !code.trim()))}>
          {mode === "login" ? at("login", lang) : at("create", lang)}
        </button>
        <button type="button" className="acct-link" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
          {mode === "login" ? at("to_signup", lang) : at("to_login", lang)}
        </button>
      </form>
    </div>
  );
}
