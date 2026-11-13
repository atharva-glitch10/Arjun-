import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChatScreen } from "./ChatScreen";
import type { ChatMsg, ChatStatus } from "./ChatScreen";

const THREAD: ChatMsg[] = [
  { id: 1, who: "me", text: "नमस्कार", time: "10:02" },
  { id: 2, who: "arjun", text: "नमस्कार, कसे आहात?", time: "10:02" },
];

function render(status: ChatStatus, extra: Partial<Parameters<typeof ChatScreen>[0]> = {}, label = "") {
  return renderToStaticMarkup(
    <ChatScreen
      title="अर्जुन"
      disclosure="AI"
      messages={THREAD}
      status={status}
      statusLabel={label}
      orbLabel="orb"
      emptyText="बोला"
      footer={<button id="rec">record</button>}
      {...extra}
    />,
  );
}

describe("ChatScreen", () => {
  it("shows her words on the right and Arjun's on the left, each with its time", () => {
    const html = render("idle");
    expect(html).toContain('data-align="end"');
    expect(html).toContain('data-align="start"');
    expect(html).toContain("नमस्कार, कसे आहात?");
    expect(html).toContain("10:02");
  });
  it("has the record control as its only action (no Stop / OK / Back)", () => {
    const html = render("idle");
    expect(html).toContain('id="rec"');
    const buttons = html.match(/<button/g) ?? [];
    expect(buttons.length).toBe(2); // the record control + the scroll-to-end button of the scroller
  });
  it("shows a spinner status line while Arjun thinks, a speaker while he talks, nothing when idle or recording", () => {
    expect(render("thinking", {}, "विचार करतोय…")).toContain('role="status"');
    expect(render("speaking", {}, "अर्जुन बोलतोय")).toContain("अर्जुन बोलतोय");
    expect(render("idle")).not.toContain("विचार");
    expect(render("recording", {}, "x")).not.toContain('data-slot="marker"');
  });
  it("replaces the record control with yes / no while Arjun waits for an answer", () => {
    const html = render("idle", { ask: { yesLabel: "हो", noLabel: "नाही", busy: false, onYes: () => undefined, onNo: () => undefined } });
    expect(html).toContain("हो");
    expect(html).toContain("नाही");
    expect(html).not.toContain('id="rec"');
  });
  it("an empty conversation shows the one prompt instead of messages", () => {
    const html = render("idle", { messages: [] });
    expect(html).toContain("बोला");
    expect(html).not.toContain('data-slot="bubble"');
  });
});
