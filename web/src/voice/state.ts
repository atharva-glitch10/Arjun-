/** Which Ghar screen the elder sees. Pure on purpose: it is the part that must never be wrong, so it is tested.
 *
 * The agent publishes its state as participant attributes: LiveKit's own "lk.agent.state" and ours,
 * "arjun.screen" + "arjun.turn" (see services/voice-agent/screenstate.py). Reasoning decides the screen;
 * the app only mirrors it.
 */

/** "reminder" / "medicine" = a delivered card (T8); "closed" = the session ended on purpose (idle), not a dropped line. */
export type AgentScreen = "reply" | "story" | "confirm" | "saved" | "safety" | "reminder" | "medicine" | "closed";
export type Phase = "idle" | "connecting" | "waiting" | "live" | "failed";
export type Failure = "connect" | "dropped" | "timeout" | "mic";
export type AgentState = "initializing" | "listening" | "thinking" | "speaking";
export type Shown =
  | "start"
  | "card"
  | "touch"
  | "home"
  | "connecting"
  | "failed"
  | "safety"
  | "listen"
  | "confirm"
  | "saved"
  | "reply"
  | "story";

export interface VoiceSnapshot {
  phase: Phase;
  failure?: Failure;
  agentState?: AgentState;
  /** Last "arjun.screen" the agent published (undefined until its first reply). */
  screen?: AgentScreen;
  /** "arjun.turn": increases with every spoken reply (0 = none yet). */
  turn: number;
  /** The turn whose safety screen the elder has acknowledged. */
  safetyDismissedTurn: number;
  /** The one-time Start tap happened on this page load (browsers allow sound only after a tap). */
  armed: boolean;
  /** A delivered reminder / medicine in SQL is still waiting for the elder to acknowledge it. */
  hasCard: boolean;
  /** The browser is blocking Arjun's audio: show "touch to hear". */
  audioBlocked: boolean;
}

/** Plain words for the elder; never a blank or frozen screen. */
export const FAILURE_TEXT: Record<Failure, string> = {
  dropped: "जोडणी तुटली, पुन्हा बोला दाबा",
  connect: "जोडणी झाली नाही, पुन्हा बोला दाबा",
  timeout: "अर्जुन अजून तयार नाही, पुन्हा बोला दाबा",
  mic: "मायक्रोफोन चालू करा, मग पुन्हा बोला दाबा",
};

const SCREENS: readonly AgentScreen[] = ["reply", "story", "confirm", "saved", "safety", "reminder", "medicine", "closed"];
const ITEM = /^(reminder|dose):\d{1,9}$/;
const STATES: readonly AgentState[] = ["initializing", "listening", "thinking", "speaking"];

/** An app / media action the agent published, exactly as the page needs it. The optional fields appear only when
 *  reasoning had them (a search result's video id, a WhatsApp contact, a control command). */
export interface ActionAttribute {
  turn: number;
  type: "open" | "control";
  kind: string;
  video_id?: string;
  value?: string;
  title?: string;
  command?: string;
  contact_id?: number;
  /** kind "app": her search words (never a URL). */
  query?: string;
}

const text = (v: unknown, max: number): string | undefined => (typeof v === "string" ? v.slice(0, max) : undefined);

/** "arjun.action" -> an action, or null when it is empty, malformed or unsafe to act on. Never throws: a bad
 *  attribute must not break the voice screen. */
export function parseActionAttribute(raw: string | undefined): ActionAttribute | null {
  if (!raw) return null;
  let o: unknown;
  try {
    o = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof o !== "object" || o === null || Array.isArray(o)) return null;
  const a = o as Record<string, unknown>;
  const turn = typeof a.turn === "number" ? a.turn : Number.parseInt(String(a.turn ?? ""), 10);
  if (!Number.isInteger(turn) || turn <= 0) return null;
  if (a.type !== "open" && a.type !== "control") return null;
  if (typeof a.kind !== "string" || !a.kind.trim()) return null;
  const action: ActionAttribute = { turn, type: a.type, kind: a.kind.trim().slice(0, 40) };
  const video = text(a.video_id, 64);
  const value = text(a.value, 500);
  const title = text(a.title, 120);
  const command = text(a.command, 40);
  if (video) action.video_id = video;
  if (value) action.value = value;
  if (title) action.title = title;
  if (command) action.command = command;
  const query = text(a.query, 100);
  if (query && !/https?:/i.test(query)) action.query = query;
  const id = typeof a.contact_id === "number" ? a.contact_id : Number.parseInt(String(a.contact_id ?? ""), 10);
  if (Number.isInteger(id) && id > 0) action.contact_id = id;
  return action;
}

/** Each action runs exactly once: only a turn newer than the last one performed (the same attribute returns after a reconnect). */
export const isFreshAction = (a: ActionAttribute, lastTurn: number): boolean => a.turn > lastTurn;

export function parseAttributes(attrs: Record<string, string>): {
  screen: AgentScreen | undefined;
  turn: number;
  agentState: AgentState | undefined;
  /** "reminder:<id>" | "dose:<id>" for a delivered card, else "". */
  item: string;
} {
  const screen = SCREENS.find((s) => s === attrs["arjun.screen"]);
  const turn = Number.parseInt(attrs["arjun.turn"] ?? "", 10);
  const agentState = STATES.find((s) => s === attrs["lk.agent.state"]);
  const rawItem = attrs["arjun.item"] ?? "";
  const item = ITEM.test(rawItem) ? rawItem : "";
  return { screen, turn: Number.isFinite(turn) && turn > 0 ? turn : 0, agentState, item };
}

export function shownFor(v: VoiceSnapshot): Shown {
  // Safety wins over every other state, including a dropped connection and a confirm card nobody answered.
  if (v.screen === "safety" && v.turn > v.safetyDismissedTurn) return "safety";
  if (v.phase === "failed") return "failed";
  // A delivered reminder / medicine stays on screen until the elder acknowledges it (SQL says when).
  const card = v.hasCard || v.screen === "reminder" || v.screen === "medicine";
  if (v.phase === "idle") return !v.armed ? "start" : v.hasCard ? "card" : "home";
  if (v.phase === "connecting" || v.phase === "waiting") return v.hasCard ? "card" : "connecting";
  if (v.audioBlocked) return "touch";
  // A spoken conversation screen wins over the card while it is current; the card comes back afterwards.
  if (v.screen && v.turn > 0 && ["reply", "story", "confirm", "saved"].includes(v.screen)) return v.screen as Shown;
  return card ? "card" : "listen";
}
