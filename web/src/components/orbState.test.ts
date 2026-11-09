import { describe, expect, it } from "vitest";

import { ORB_LABELS, orbLabel } from "@/elder/i18n";
import type { AgentState, Phase } from "@/voice/state";

import { ORB_STATES, orbStateFor } from "./orbState";

describe("orbStateFor", () => {
  it("is idle when no session is open, and after a failure", () => {
    expect(orbStateFor("idle", undefined)).toBe("idle");
    expect(orbStateFor("failed", "listening")).toBe("idle");
  });

  it("is connecting while the session is being opened", () => {
    expect(orbStateFor("connecting", undefined)).toBe("connecting");
    expect(orbStateFor("waiting", "listening")).toBe("connecting");
  });

  it("mirrors the agent state once live", () => {
    const live: Array<[AgentState | undefined, string]> = [
      ["listening", "listening"],
      ["thinking", "thinking"],
      ["speaking", "speaking"],
      ["initializing", "connecting"],
      [undefined, "connecting"],
    ];
    for (const [agent, orb] of live) expect(orbStateFor("live", agent)).toBe(orb);
  });

  it("always returns a known state", () => {
    const phases: Phase[] = ["idle", "connecting", "waiting", "live", "failed"];
    const agents: Array<AgentState | undefined> = ["initializing", "listening", "thinking", "speaking", undefined];
    for (const p of phases) for (const a of agents) expect(ORB_STATES).toContain(orbStateFor(p, a));
  });
});

describe("orb labels", () => {
  it("exist in Marathi, Hindi and English for every state", () => {
    for (const lang of ["mr", "hi", "en"] as const) {
      for (const s of ORB_STATES) expect(ORB_LABELS[lang][s].length).toBeGreaterThan(0);
    }
  });
  it("fall back to English for an unknown language", () => {
    expect(orbLabel("xx", "listening")).toBe(ORB_LABELS.en.listening);
    expect(orbLabel("ta", "listening")).toBe(ORB_LABELS.ta.listening);
    expect(orbLabel("mr", "listening")).toBe("मी ऐकतोय");
  });
});
