import { KahaniScreen, ListenScreen } from "@/screens/ElderScreens";
import type { ChatMsg } from "@/screens/ElderScreens";

const THREAD: ChatMsg[] = [
  { id: 1, who: "me", text: "आज मी दिवाळीचा फराळ केला", time: "10:02" },
  { id: 2, who: "arjun", text: "अरे वा! कोणते पदार्थ केलेत?", time: "10:02" },
  { id: 3, who: "me", text: "चकली आणि लाडू", time: "10:03" },
  { id: 4, who: "arjun", text: "मस्तच! आर्यनला लाडू खूप आवडतात ना?", time: "10:03" },
];

/** Dev preview of the WhatsApp-style conversation (?ui=chat). */
export function ChatDemo() {
  return (
    <div className="elder-shell" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 24 }}>
      <ListenScreen heard="आणि शंकरपाळे पण" onStop={() => undefined} thread={THREAD} />
      <KahaniScreen prompt="" noteTitle="" transcript="" hint="" thread={THREAD} onSpeak={() => undefined} onBack={() => undefined} />
    </div>
  );
}
