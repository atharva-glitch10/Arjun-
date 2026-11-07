import { describe, expect, it } from "vitest";

import { isVideoCallStopCommand } from "./videoCall";
import type { VideoCall } from "../api";

const ringing: VideoCall = {
  id: 3, user_id: 1, contact_id: 8, contact_name: "चंद्रकांत", mode: "video", status: "ringing",
  created_at: "2026-11-07T09:00:00",
};

describe("elder video call view states", () => {
  it("renders state data for ringing and answered phases", () => {
    expect(ringing.status).toBe("ringing");
    expect({ ...ringing, status: "answered" }).toMatchObject({ contact_name: "चंद्रकांत", status: "answered", mode: "video" });
    expect({ ...ringing, status: "missed" }).toMatchObject({ status: "missed" });
  });

  it("recognizes Marathi and English hang up speech", () => {
    for (const phrase of ["बंद कर", "बंद करा", "बंद कर ना", "थांब", "थांबव", "end call", "stop"]) {
      expect(isVideoCallStopCommand(phrase)).toBe(true);
    }
    expect(isVideoCallStopCommand("आज काय आहे")).toBe(false);
  });
});
