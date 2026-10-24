import { describe, expect, it, vi } from "vitest";

import { confirmThen } from "./guard";

describe("confirm before a risky click", () => {
  it("does nothing when the person says no", async () => {
    const action = vi.fn(async () => 1);
    const ask = vi.fn(() => false);
    expect(await confirmThen(ask, "sure?", action)).toBeUndefined();
    expect(ask).toHaveBeenCalledWith("sure?");
    expect(action).not.toHaveBeenCalled();
  });

  it("runs the action once when the person says yes", async () => {
    const action = vi.fn(async () => 7);
    expect(await confirmThen(() => true, "sure?", action)).toBe(7);
    expect(action).toHaveBeenCalledTimes(1);
  });
});
