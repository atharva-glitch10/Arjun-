import type { AgentState, Phase } from "@/voice/state";

/** What the orb shows. A pure mapping from the voice hook's existing snapshot: it adds no voice logic. */
export type OrbState = "idle" | "connecting" | "listening" | "thinking" | "speaking";

export const ORB_STATES: readonly OrbState[] = ["idle", "connecting", "listening", "thinking", "speaking"];

export function orbStateFor(phase: Phase, agentState: AgentState | undefined): OrbState {
  if (phase === "connecting" || phase === "waiting") return "connecting";
  if (phase !== "live") return "idle"; // idle, or failed (the failure text is shown elsewhere)
  switch (agentState) {
    case "listening":
      return "listening";
    case "thinking":
      return "thinking";
    case "speaking":
      return "speaking";
    default:
      return "connecting"; // live, but the agent has not said it is ready yet
  }
}
