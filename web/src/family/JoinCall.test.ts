import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("livekit-client", () => ({
  Room: class Room {},
  RoomEvent: { TrackSubscribed: "trackSubscribed" },
  Track: { Source: { Camera: "camera" }, Kind: { Audio: "audio" } },
}));

import { JoinCall } from "./JoinCall";

describe("family video join page", () => {
  it("renders a mobile-friendly join state before LiveKit connects", () => {
    const html = renderToStaticMarkup(createElement(JoinCall));
    expect(html).toContain("घरच्यांशी बोला");
    expect(html).toContain("जोडत आहे");
    expect(html).toContain("join-shell");
  });
});
