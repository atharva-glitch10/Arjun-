/** Which Ghar screen the elder sees. Pure on purpose: it is the part that must never be wrong, so it is tested.
 *
 * The agent publishes its state as participant attributes: LiveKit's own "lk.agent.state" and ours,
 * "arjun.screen" + "arjun.turn" (see services/voice-agent/screenstate.py). Reasoning decides the screen;
 * the app only mirrors it.
 */

export type AgentScreen = "reply" | "story" | "confirm" | "saved" | "safety";
export type Phase = "idle" | "connecting" | "waiting" | "live" | "failed";
export type Failure = "connect" | "dropped" | "timeout" | "mic";
export type AgentState = "initializing" | "listening" | "thinking" | "speaking";
export type Shown =
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
}

/** Plain words for the elder; never a blank or frozen screen. */
export const FAILURE_TEXT: Record<Failure, string> = {
  dropped: "जोडणी तुटली, पुन्हा बोला दाबा",
  connect: "जोडणी झाली नाही, पुन्हा बोला दाबा",
  timeout: "अर्जुन अजून तयार नाही, पुन्हा बोला दाबा",
  mic: "मायक्रोफोन चालू करा, मग पुन्हा बोला दाबा",
};

const SCREENS: readonly AgentScreen[] = ["reply", "story", "confirm", "saved", "safety"];
const STATES: readonly AgentState[] = ["initializing", "listening", "thinking", "speaking"];

export function parseAttributes(attrs: Record<string, string>): {
  screen: AgentScreen | undefined;
  turn: number;
  agentState: AgentState | undefined;
} {
  const screen = SCREENS.find((s) => s === attrs["arjun.screen"]);
  const turn = Number.parseInt(attrs["arjun.turn"] ?? "", 10);
  const agentState = STATES.find((s) => s === attrs["lk.agent.state"]);
  return { screen, turn: Number.isFinite(turn) && turn > 0 ? turn : 0, agentState };
}

export function shownFor(v: VoiceSnapshot): Shown {
  // Safety wins over every other state, including a dropped connection and a confirm card nobody answered.
  if (v.screen === "safety" && v.turn > v.safetyDismissedTurn) return "safety";
  if (v.phase === "failed") return "failed";
  if (v.phase === "idle") return "home";
  if (v.phase === "connecting" || v.phase === "waiting") return "connecting";
  if (!v.screen || v.turn === 0 || v.screen === "safety") return "listen"; // "safety" here = already dismissed
  return v.screen;
}
