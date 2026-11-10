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

describe("the screen language goes to the backend in the request body", () => {
  afterEach(() => vi.unstubAllGlobals());
  const token = { url: "wss://x", token: "t", room: "r", identity: "elder-1", expires_in: 60 };

  it("sends language with the LiveKit token request, so the voice agent can reply in it", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => token });
    vi.stubGlobal("fetch", fetchMock);
    await api.livekitToken(1, "hi");
    expect(fetchMock).toHaveBeenCalledWith(
      "/core/livekit/token",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ user_id: 1, language: "hi" }) }),
    );
  });

  it("sends nothing extra when no language is known (older behaviour)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => token });
    vi.stubGlobal("fetch", fetchMock);
    await api.livekitToken(1);
    expect(fetchMock).toHaveBeenCalledWith("/core/livekit/token", expect.objectContaining({ body: JSON.stringify({ user_id: 1 }) }));
  });
});
