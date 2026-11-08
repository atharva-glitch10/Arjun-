import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import type { ClonedVoice } from "../api";

const CONSENT =
  "I am the person whose voice this is, or I have their clear permission. Arjun may speak in this voice to my family " +
  "member in friendly conversation only — never for emergency, medicine or money messages — and it can be deleted anytime.";
const MIN_S = 10;
const MAX_S = 45;

/** Any browser recording (Chrome records WebM/Opus) -> 16-bit mono WAV at 24 kHz, a format Gnani documents.
 * Decoding happens locally in the browser; nothing leaves the page until the family clicks Create. */
async function toWav(blob: Blob): Promise<Blob> {
  const RATE = 24000;
  const decoded = await new AudioContext().decodeAudioData(await blob.arrayBuffer());
  const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * RATE), RATE);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start();
  const pcm = (await offline.startRendering()).getChannelData(0);
  const out = new DataView(new ArrayBuffer(44 + pcm.length * 2));
  const text = (o: number, t: string) => [...t].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
  text(0, "RIFF");
  out.setUint32(4, 36 + pcm.length * 2, true);
  text(8, "WAVEfmt ");
  out.setUint32(16, 16, true);
  out.setUint16(20, 1, true);
  out.setUint16(22, 1, true);
  out.setUint32(24, RATE, true);
  out.setUint32(28, RATE * 2, true);
  out.setUint16(32, 2, true);
  out.setUint16(34, 16, true);
  text(36, "data");
  out.setUint32(40, pcm.length * 2, true);
  pcm.forEach((v, i) => out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, v)) * 0x7fff, true));
  return new Blob([out], { type: "audio/wav" });
}

/** Read a Blob as plain base64 (no data: prefix). */
function toBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] ?? "");
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

/** "A familiar voice": a family member records 10-30 s, confirms consent, and Arjun can chat in that voice (Gnani
 * voice cloning). The recording is sent once and never stored; emergencies and medicines always use Arjun's voice. */
export function VoicesCard({ userId, name }: { userId: number; name: string }) {
  const [voices, setVoices] = useState<ClonedVoice[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [who, setWho] = useState("");
  const [relation, setRelation] = useState("");
  const [consentBy, setConsentBy] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [clip, setClip] = useState<Blob | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [recording, setRecording] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      setVoices(await api.voices(userId));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load");
    }
  }, [userId]);

  useEffect(() => {
    void load();
    return () => window.clearInterval(timer.current);
  }, [load]);

  const stop = () => {
    rec.current?.stop();
    window.clearInterval(timer.current);
    setRecording(false);
  };

  const start = async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const r = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setClip(new Blob(chunks, { type: r.mimeType || "audio/webm" }));
      };
      rec.current = r;
      setClip(null);
      setSeconds(0);
      r.start();
      setRecording(true);
      const t0 = Date.now();
      timer.current = window.setInterval(() => {
        const s = Math.floor((Date.now() - t0) / 1000);
        setSeconds(s);
        if (s >= MAX_S) stop();
      }, 250);
    } catch {
      setError("Microphone not available. Allow the mic, or upload a recording instead.");
    }
  };

  const pickFile = (f: File | undefined) => {
    if (!f) return;
    setClip(f);
    setSeconds(0);
  };

  const clipUrl = useMemo(() => (clip ? URL.createObjectURL(clip) : ""), [clip]);
  useEffect(() => () => (clipUrl ? URL.revokeObjectURL(clipUrl) : undefined), [clipUrl]);

  const ready = clip !== null && who.trim() && consentBy.trim() && agreed && !busy && (seconds === 0 || seconds >= MIN_S);

  const save = async () => {
    if (!clip || !ready) return;
    setBusy(true);
    setError("");
    try {
      let wav: Blob;
      try {
        wav = await toWav(clip);
      } catch {
        throw new Error("Could not read this recording. Please record again, or upload a WAV or MP3 file.");
      }
      await api.addVoice(userId, {
        name: who.trim(),
        relation: relation.trim(),
        consent: true,
        consent_by: consentBy.trim(),
        audio_base64: await toBase64(wav),
        mime: "audio/wav",
      });
      setWho("");
      setRelation("");
      setConsentBy("");
      setAgreed(false);
      setClip(null);
      setSeconds(0);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add the voice");
    } finally {
      setBusy(false);
    }
  };

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      await load();
    }
  };

  return (
    <section className="fam-card voices-card" style={{ flex: "1 1 520px" }}>
      <h2>A familiar voice</h2>
      <p className="fam-note" style={{ marginTop: 0 }}>
        Let Arjun chat with {name} in your voice. Emergencies, medicines and reminders always stay in Arjun&apos;s own voice,
        and {name}&apos;s screen always shows whose voice is speaking.
      </p>

      <ul className="fam-list">
        {voices.length === 0 && <li>No familiar voice yet. Arjun speaks in its own voice.</li>}
        {voices.map((v) => (
          <li key={v.id} className="voice-row">
            <div>
              <strong>{v.name}</strong>
              {v.relation && <> · {v.relation}</>}
              {v.active && <span className="voice-on">In use</span>}
              <div className="fam-note" style={{ margin: "4px 0 0" }}>
                Consent by {v.consent_by} · used {v.use_count} time{v.use_count === 1 ? "" : "s"}
              </div>
            </div>
            <div className="voice-actions">
              <button onClick={() => void act(() => api.setVoiceActive(userId, v.id, !v.active))}>
                {v.active ? "Stop using" : "Use this voice"}
              </button>
              <button
                className="danger"
                onClick={() => {
                  if (window.confirm(`Delete ${v.name}'s voice? This cannot be undone.`))
                    void act(() => api.deleteVoice(userId, v.id));
                }}
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>

      <h3 style={{ marginBottom: 8 }}>Add a voice</h3>
      <div className="voice-form">
        <label>
          Name {name} calls them
          <input value={who} onChange={(e) => setWho(e.target.value)} placeholder="Rahul" maxLength={80} />
        </label>
        <label>
          Relation
          <input value={relation} onChange={(e) => setRelation(e.target.value)} placeholder="son" maxLength={40} />
        </label>
      </div>
      <p className="fam-note">
        Record 10–30 seconds of the person talking naturally in a quiet room, e.g. telling {name} about their day.
      </p>
      <div className="voice-record">
        {!recording ? (
          <button onClick={() => void start()} disabled={busy}>
            ● Record
          </button>
        ) : (
          <button className="danger" onClick={stop}>
            ■ Stop ({seconds}s)
          </button>
        )}
        <label className="voice-upload">
          or upload a file
          <input type="file" accept="audio/*" onChange={(e) => pickFile(e.target.files?.[0])} />
        </label>
        {clip && !recording && <audio controls src={clipUrl} />}
      </div>
      {clip && seconds > 0 && seconds < MIN_S && <p className="fam-note">Too short: please record at least {MIN_S} seconds.</p>}

      <div className="voice-consent">
        <label>
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <span>{CONSENT}</span>
        </label>
        <label>
          Full name of the person giving consent
          <input value={consentBy} onChange={(e) => setConsentBy(e.target.value)} placeholder="Rahul Patil" maxLength={120} />
        </label>
      </div>
      <button className="primary" disabled={!ready} onClick={() => void save()}>
        {busy ? "Creating voice…" : "Create voice with Gnani"}
      </button>
      {error && (
        <p className="fam-note" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
