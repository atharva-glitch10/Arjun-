/** Browser side of the emergency alarm: a repeating tone, a system pop-up and a flashing tab title.
 *
 * The tone is plain Web Audio beeps (no speech of any kind, so scripts/check_no_browser_speech.py still
 * holds). Browsers only allow sound after a tap, so the family taps "Turn on emergency alarm" once per page
 * load; the pop-up needs permission once per browser. Without either, the red banner is still shown.
 */

type Ctx = AudioContext;

let ctx: Ctx | null = null;
let beepTimer: number | null = null;
let titleTimer: number | null = null;
let baseTitle = "";

function audio(): Ctx | null {
  if (ctx) return ctx;
  const C = (window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext) as
    | typeof AudioContext
    | undefined;
  if (!C) return null;
  ctx = new C();
  return ctx;
}

/** Call from a tap: unlocks sound and asks for pop-up permission. Returns what is now available. */
export async function enableAlarm(): Promise<{ sound: boolean; popup: boolean }> {
  const c = audio();
  let sound = false;
  if (c) {
    try {
      await c.resume();
      sound = c.state === "running";
    } catch {
      sound = false;
    }
  }
  let popup = false;
  if ("Notification" in window) {
    try {
      popup = (Notification.permission === "default" ? await Notification.requestPermission() : Notification.permission) === "granted";
    } catch {
      popup = false;
    }
  }
  return { sound, popup };
}

export function alarmState(): { sound: boolean; popup: boolean } {
  return {
    sound: ctx?.state === "running",
    popup: "Notification" in window && Notification.permission === "granted",
  };
}

function beep(c: Ctx, at: number, freq: number): void {
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = "square";
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(0.25, at + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.35);
  osc.connect(gain).connect(c.destination);
  osc.start(at);
  osc.stop(at + 0.4);
}

function ring(): void {
  const c = ctx;
  if (!c || c.state !== "running") return;
  const t = c.currentTime + 0.05;
  beep(c, t, 880);
  beep(c, t + 0.45, 660);
  beep(c, t + 0.9, 880);
}

/** Start (or keep) the alarm going. Idempotent. */
export function startAlarm(): void {
  if (beepTimer === null) {
    ring();
    beepTimer = window.setInterval(ring, 3_000);
  }
  if (titleTimer === null) {
    baseTitle = document.title;
    let on = false;
    titleTimer = window.setInterval(() => {
      on = !on;
      document.title = on ? "!! EMERGENCY - Arjun !!" : baseTitle;
    }, 1_000);
  }
}

export function stopAlarm(): void {
  if (beepTimer !== null) window.clearInterval(beepTimer);
  if (titleTimer !== null) {
    window.clearInterval(titleTimer);
    document.title = baseTitle || document.title;
  }
  beepTimer = null;
  titleTimer = null;
}

/** One system pop-up per emergency. Clicking it brings the dashboard to the front. */
export function popup(id: number, body: string): void {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  try {
    const n = new Notification("EMERGENCY - Arjun", { body, tag: `arjun-emergency-${id}`, requireInteraction: true });
    n.onclick = () => {
      window.focus();
      n.close();
    };
  } catch {
    // some mobile browsers only allow pop-ups from a service worker; the banner and sound still work
  }
}
