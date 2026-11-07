import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";

describe("daily Telegram briefing API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks core-api to force-send from the dashboard action", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: "sent" }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.sendBriefing(1, true)).resolves.toEqual({ status: "sent" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/core/users/1/briefing/send",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ force: true }) }),
    );
  });
});
