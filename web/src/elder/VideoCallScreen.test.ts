import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("livekit-client", () => ({
  RoomEvent: { TrackSubscribed: "trackSubscribed", TrackUnsubscribed: "trackUnsubscribed" },
  Track: { Source: { Camera: "camera" }, Kind: { Video: "video" } },
}));

import type { VideoCall } from "../api";
import { VideoCallScreen } from "./VideoCallScreen";

const call = (status: VideoCall["status"]): VideoCall => ({
  id: 3, user_id: 1, contact_id: 9, contact_name: "चंद्रकांत", mode: "video", status,
  created_at: "2026-11-07T09:00:00",
});

describe("elder video call screen", () => {
  it("shows the ringing preview, contact, and hangup control", () => {
    const html = renderToStaticMarkup(
      createElement(VideoCallScreen, { call: call("ringing"), starting: null, room: null, userId: 1, onEnd: () => {}, onMissed: () => {} }),
    );
    expect(html).toContain("चंद्रकांतला बोलावतोय");
    expect(html).toContain("बंद करा");
    expect(html).toContain("elder-call-wait");
  });

  it("shows the full family video layout after answer", () => {
    const html = renderToStaticMarkup(
      createElement(VideoCallScreen, { call: call("answered"), starting: null, room: null, userId: 1, onEnd: () => {}, onMissed: () => {} }),
    );
    expect(html).toContain("elder-family-video");
    expect(html).toContain("elder-self-video");
  });
});
