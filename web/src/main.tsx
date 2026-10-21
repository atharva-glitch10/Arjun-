import { useState } from "react";
import { createRoot } from "react-dom/client";

import { Dashboard } from "./family/Dashboard";
import { ElderApp } from "./elder/ElderApp";
import { Gallery } from "./ghar/Gallery";
import "./styles/ghar.css";

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
        style={{ display: "flex", gap: 6, justifyContent: "flex-end", padding: 12, background: "var(--ghar-ground)" }}
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
if (root) createRoot(root).render(params.has("preview") ? <Gallery /> : <App />);
