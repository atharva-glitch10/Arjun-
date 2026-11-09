import { useState } from "react";
import { createRoot } from "react-dom/client";

import { Dashboard } from "./family/Dashboard";
import { JoinCall } from "./family/JoinCall";
import { ElderApp } from "./elder/ElderApp";
import { ChatDemo } from "./preview/ChatDemo";
import { UiGallery } from "./preview/UiGallery";
import { YtDebug } from "./preview/YtDebug";
import "./styles/app.css";
import "./styles/ui.css";

type View = "elder" | "caregiver";

try {
  if (localStorage.getItem("arjun_reduce_motion") === "1") document.documentElement.classList.add("no-motion");
} catch {
  // storage blocked: animations stay on (still respect prefers-reduced-motion)
}

const params = new URLSearchParams(window.location.search);

function App() {
  const [view, setView] = useState<View>(params.get("view") === "family" ? "caregiver" : "elder");
  const [userId, setUserId] = useState<number>(() => {
    const fromUrl = Number(params.get("user"));
    if (Number.isInteger(fromUrl) && fromUrl > 0) return fromUrl;
    let saved = 0;
    try {
      saved = Number(localStorage.getItem("arjun_user_id"));
    } catch {
      // ignore
    }
    return Number.isInteger(saved) && saved > 0 ? saved : 1;
  });

  const changeUser = (id: number) => {
    setUserId(id);
    try {
      localStorage.setItem("arjun_user_id", String(id));
    } catch {
      // ignore
    }
  };

  const evening = params.get("theme") === "evening" ? true : undefined;

  return (
    <>
      {view === "elder" ? <ElderApp userId={userId} forceEvening={evening} /> : <Dashboard userId={userId} onUser={changeUser} />}
      <nav
        aria-label="Switch view"
        style={{ display: "flex", gap: 6, justifyContent: "flex-end", padding: 12, background: "var(--ground-app)" }}
      >
        <button className="fbtn" style={{ minHeight: 44 }} onClick={() => setView(view === "elder" ? "caregiver" : "elder")}>
          {view === "elder" ? "Family dashboard" : "Elder screen"}
        </button>
        <input
          className="fam-input"
          type="number"
          min={1}
          aria-label="User id"
          value={userId}
          onChange={(e) => changeUser(Math.max(1, Number(e.target.value) || 1))}
          style={{ width: 64 }}
        />
      </nav>
    </>
  );
}

const root = document.getElementById("root");
if (root) {
  const join = params.get("view") === "join";
  createRoot(root).render(join ? <JoinCall /> : params.get("ui") === "1" ? <UiGallery /> : params.get("ui") === "chat" ? <ChatDemo /> : (import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV === true && params.get("debug") === "yt" ? <YtDebug /> : <App />);
}
