import { describe, expect, it } from "vitest";

import { FAILURE_TEXT, parseAttributes, shownFor } from "./state";
import type { VoiceSnapshot } from "./state";

const base: VoiceSnapshot = { phase: "live", agentState: "listening", turn: 0, safetyDismissedTurn: 0 };
const snap = (o: Partial<VoiceSnapshot>): VoiceSnapshot => ({ ...base, ...o });

describe("which Ghar screen is shown", () => {
  it("is home before anyone taps बोला", () => {
    expect(shownFor(snap({ phase: "idle" }))).toBe("home");
  });

  it("says Arjun is getting ready while connecting or waiting for the agent", () => {
    expect(shownFor(snap({ phase: "connecting" }))).toBe("connecting");
    expect(shownFor(snap({ phase: "waiting" }))).toBe("connecting");
  });

  it("listens once the agent is up and has said nothing yet", () => {
    expect(shownFor(snap({}))).toBe("listen");
    expect(shownFor(snap({ agentState: "thinking" }))).toBe("listen");
  });

  it("mirrors the screen the agent published", () => {
    for (const screen of ["reply", "story", "confirm", "saved"] as const) {
      expect(shownFor(snap({ screen, turn: 1 }))).toBe(screen);
    }
  });

  it("keeps the confirm card while Arjun speaks or waits for the answer", () => {
    for (const agentState of ["speaking", "listening", "thinking"] as const) {
      expect(shownFor(snap({ screen: "confirm", turn: 2, agentState }))).toBe("confirm");
    }
  });
});

describe("safety wins over every other state", () => {
  it("replaces a confirm card the user never answered, with nothing tapped", () => {
    expect(shownFor(snap({ screen: "confirm", turn: 2 }))).toBe("confirm");
    expect(shownFor(snap({ screen: "safety", turn: 3 }))).toBe("safety");
  });

  it("wins while Arjun is speaking, thinking or listening", () => {
    for (const agentState of ["speaking", "thinking", "listening", "initializing"] as const) {
      expect(shownFor(snap({ screen: "safety", turn: 3, agentState }))).toBe("safety");
    }
  });

  it("stays visible even if the connection drops or is retried", () => {
    for (const phase of ["failed", "connecting", "waiting"] as const) {
      expect(shownFor(snap({ phase, failure: "dropped", screen: "safety", turn: 3 }))).toBe("safety");
    }
  });

  it("goes away only when the elder dismisses THAT reply, and comes back for the next one", () => {
    expect(shownFor(snap({ screen: "safety", turn: 3, safetyDismissedTurn: 3 }))).toBe("listen");
    expect(shownFor(snap({ screen: "safety", turn: 4, safetyDismissedTurn: 3 }))).toBe("safety");
  });
});

describe("a dropped or failed connection is never blank", () => {
  it("shows the plain failure screen for every failure kind", () => {
    for (const failure of ["connect", "dropped", "timeout", "mic"] as const) {
      expect(shownFor(snap({ phase: "failed", failure }))).toBe("failed");
      expect(FAILURE_TEXT[failure].length).toBeGreaterThan(5);
    }
  });

  it("uses the agreed wording for a dropped connection", () => {
    expect(FAILURE_TEXT.dropped).toBe("जोडणी तुटली, पुन्हा बोला दाबा");
  });
});

describe("reading the agent's attributes", () => {
  it("parses screen, turn and the built-in agent state", () => {
    expect(parseAttributes({ "arjun.screen": "confirm", "arjun.turn": "4", "lk.agent.state": "speaking" })).toEqual({
      screen: "confirm",
      turn: 4,
      agentState: "speaking",
    });
  });

  it("ignores anything it does not know", () => {
    expect(parseAttributes({ "arjun.screen": "<script>", "arjun.turn": "x", "lk.agent.state": "dancing" })).toEqual({
      screen: undefined,
      turn: 0,
      agentState: undefined,
    });
    expect(parseAttributes({})).toEqual({ screen: undefined, turn: 0, agentState: undefined });
  });
});
