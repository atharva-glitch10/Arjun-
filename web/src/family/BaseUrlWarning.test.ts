import { describe, expect, it } from "vitest";

import type { BaseUrlDiag } from "../api";
import { baseUrlMessage } from "./BaseUrlWarning";

const base: BaseUrlDiag = {
  url: "https://dead.trycloudflare.com", https: true, reachable: false, kind: "quick-tunnel", ok: false,
  reason: "BASE_URL is a trycloudflare.com quick tunnel", hint: "Fix: set BASE_URL to the Tailscale Funnel URL (https://odin.tail7a9105.ts.net).",
};

describe("call-link warning banner", () => {
  it("says what is wrong and how to fix it when the link is not ok", () => {
    const m = baseUrlMessage(base);
    expect(m).toContain("Family-call links are not working");
    expect(m).toContain("quick tunnel");
    expect(m).toContain("odin.tail7a9105.ts.net");
  });
  it("is silent when the link is ok or the check could not run", () => {
    expect(baseUrlMessage({ ...base, ok: true, reachable: true, kind: "tailscale", reason: "" })).toBe("");
    expect(baseUrlMessage(null)).toBe("");
  });
});
