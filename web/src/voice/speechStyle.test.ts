import { describe, expect, it } from "vitest";
import { playbackVolume } from "./speechStyle";

describe("family speech volume preference", () => {
  it("boosts Arjun audio for loud speech and restores the saved player level", () => {
    expect(playbackVolume({ volume: "loud" }, 0.6)).toBe(1);
    expect(playbackVolume({ volume: "normal" }, 0.6)).toBe(0.6);
  });
});
