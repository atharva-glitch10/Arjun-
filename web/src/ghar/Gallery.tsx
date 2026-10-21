import type { ReactNode } from "react";

import {
  ConfirmScreen,
  DoneScreen,
  HomeScreen,
  KahaniScreen,
  ListenScreen,
  MedicineScreen,
  VitalsScreen,
} from "./Screens";

// Design review only (open /?preview). Every value below is synthetic sample copy from the mockups;
// the real app never reads from here. Medicine dose is a placeholder on purpose.
const noop = () => undefined;

function Frame({ title, children, night = false, listening = false }: { title: string; children: ReactNode; night?: boolean; listening?: boolean }) {
  return (
    <figure>
      <figcaption>{title}</figcaption>
      <div className="frame">
        <div className={`elder-shell${night ? " night" : ""}${listening ? " listening" : ""}`}>{children}</div>
      </div>
    </figure>
  );
}

export function Gallery() {
  return (
    <div className="gallery">
      <Frame title="Home (morning)">
        <HomeScreen
          evening={false}
          greeting="शुभ सकाळ, आजी"
          dateLine="मंगळवार, १३ ऑक्टोबर"
          clock="सकाळी ९:१५"
          items={[
            { key: "1", when: "दुपारी ४ वाजता", what: "राहुलला फोन", initials: "रा", kind: "call" },
            { key: "2", when: "उद्या सकाळी १० वाजता", what: "डॉक्टरकडे", kind: "appointment" },
          ]}
          onSpeak={noop}
          onToday={noop}
          onHelp={noop}
        />
      </Frame>
      <Frame title="Home (evening)" night>
        <HomeScreen
          evening
          greeting="शुभ संध्याकाळ, आजी"
          dateLine="मंगळवार"
          clock="संध्याकाळी ७:१०"
          items={[]}
          medicine={{ when: "रात्री जेवणानंतर · ८:४५", name: "[औषधाचे नाव]" }}
          onSpeak={noop}
          onToday={noop}
          onHelp={noop}
        />
      </Frame>
      <Frame title="Listening" listening>
        <ListenScreen heard="उद्या सकाळी १० वाजता डॉक्टरकडे जायचं आहे, आठवण कर" onDone={noop} onStop={noop} />
      </Frame>
      <Frame title="Confirm">
        <ConfirmScreen dayLabel="उद्या · बुधवार" timeLabel="सकाळी १०:००" task="डॉक्टरकडे जायचं" onYes={noop} onNo={noop} onReplay={noop} />
      </Frame>
      <Frame title="Saved">
        <DoneScreen title="आठवण ठेवली!" line="उद्या सकाळी मी तुम्हाला सांगेन" onOk={noop} />
      </Frame>
      <Frame title="Medicine due">
        <MedicineScreen status="due" timeLabel="दुपारी १:१५" name="[औषधाचे नाव]" dose="[डोस]" mealNote="जेवण झालं ना? मग आता" onTaken={noop} onSnooze={noop} onOk={noop} />
      </Frame>
      <Frame title="Medicine taken">
        <MedicineScreen status="taken" timeLabel="" name="" dose="" nextLine="पुढचं औषध रात्री जेवणानंतर" onTaken={noop} onSnooze={noop} onOk={noop} />
      </Frame>
      <Frame title="Medicine snoozed">
        <MedicineScreen status="snoozed" timeLabel="" name="" dose="" snoozeUntil="१:३०" onTaken={noop} onSnooze={noop} onOk={noop} />
      </Frame>
      <Frame title="BP confirm">
        <VitalsScreen status="confirm" timeNote="सकाळी ९:०० · नाश्त्याआधी" said="एकशे बेचाळीस बाय अठ्ठ्याऐंशी, पल्स शहात्तर" bp="१४२/८८" pulse="७६" familyName="राहुल" onYes={noop} onRetry={noop} onOk={noop} />
      </Frame>
      <Frame title="BP saved">
        <VitalsScreen status="saved" timeNote="" said="" bp="" familyName="राहुल" onYes={noop} onRetry={noop} onOk={noop} />
      </Frame>
      <Frame title="Kahani (story + share)">
        <KahaniScreen
          prompt="आजी, आज धपाटे करायचे का? तुमची रेसिपी मला शिकवा ना?"
          noteTitle="मंगळवार · धपाटे"
          transcript="ज्वारीचं पीठ घ्यायचं, त्यात थोडं बेसन. कांदा बारीक चिरायचा, मेथी घालायची…"
          hint="ऐकतोय… सावकाश सांगा"
          share={{ names: ["नेहा", "आर्यन"], initials: ["ने", "आ"], onYes: noop, onNo: noop }}
          onBack={noop}
        />
      </Frame>
    </div>
  );
}
