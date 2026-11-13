import { Mic } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ChatScreen } from "@/screens/ChatScreen";
import type { ChatMsg, ChatStatus } from "@/screens/ChatScreen";

const THREAD: ChatMsg[] = [
  { id: 1, who: "me", text: "आज मी दिवाळीचा फराळ केला", time: "10:02" },
  { id: 2, who: "arjun", text: "अरे वा! कोणते पदार्थ केलेत?", time: "10:02" },
  { id: 3, who: "me", text: "चकली आणि लाडू", time: "10:03" },
  { id: 4, who: "arjun", text: "मस्तच! आर्यनला लाडू खूप आवडतात ना?", time: "10:03" },
];

const record = (
  <Button size="lg" className="w-full">
    <Mic aria-hidden /> बोला
  </Button>
);

function Demo({ status, label, ask, messages = THREAD }: { status: ChatStatus; label: string; ask?: boolean; messages?: ChatMsg[] }) {
  return (
    <ChatScreen
      title="अर्जुन"
      disclosure="अर्जुन — तुमचा AI सोबती"
      messages={messages}
      status={status}
      statusLabel={label}
      orbLabel={label || "अर्जुन तयार आहे"}
      emptyText="बोला"
      ask={ask ? { yesLabel: "हो", noLabel: "नाही", busy: false, onYes: () => undefined, onNo: () => undefined } : undefined}
      footer={record}
    />
  );
}

/** Dev preview of the /chat screen in its states (?ui=chat). */
export function ChatDemo() {
  return (
    <div className="elder-shell" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 24 }}>
      <Demo status="idle" label="" messages={[]} />
      <Demo status="thinking" label="विचार करतोय…" />
      <Demo status="speaking" label="अर्जुन बोलतोय" />
      <Demo status="idle" label="" ask />
    </div>
  );
}
