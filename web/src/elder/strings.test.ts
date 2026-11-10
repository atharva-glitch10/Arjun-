import { afterEach, describe, expect, it } from "vitest";

import { dateLine, dayWord, periodOfDay, spokenTime, timeLabel, weekday } from "./format";
import { elderLanguage, orbLabel, timeGreeting } from "./i18n";
import { ALL_STRING_KEYS, ELDER_LANGUAGES, LANGUAGE_NAMES, getElderLang, setElderLang, t, uiLanguage } from "./strings";

afterEach(() => setElderLang("mr"));

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("elder strings: all ten Gnani languages", () => {
  it("has exactly mr hi en bn gu kn ml pa ta te, each with a name in its own script", () => {
    expect([...ELDER_LANGUAGES]).toEqual(["mr", "hi", "en", "bn", "gu", "kn", "ml", "pa", "ta", "te"]);
    for (const l of ELDER_LANGUAGES) expect(LANGUAGE_NAMES[l].length).toBeGreaterThan(1);
  });

  it("every key has a non-empty line in every language, with the same {placeholders} as English", () => {
    for (const key of ALL_STRING_KEYS) {
      const en = placeholders(t(key, undefined, "en"));
      for (const lang of ELDER_LANGUAGES) {
        const line = t(key, undefined, lang);
        expect(line.trim().length, `${key}/${lang}`).toBeGreaterThan(0);
        expect(placeholders(line), `${key}/${lang}`).toEqual(en);
      }
    }
  });

  it("new languages are really translated, not copies of English or Marathi", () => {
    for (const lang of ["bn", "gu", "kn", "ml", "pa", "ta", "te"] as const) {
      for (const key of ["ok", "speak", "help", "stop", "meds", "start_btn"] as const) {
        expect(t(key, undefined, lang)).not.toBe(t(key, undefined, "en"));
        expect(t(key, undefined, lang)).not.toBe(t(key, undefined, "mr"));
      }
    }
  });

  it("keeps the original Marathi wording", () => {
    expect(t("speak", undefined, "mr")).toBe("बोला");
    expect(t("ok", undefined, "mr")).toBe("ठीक आहे");
    expect(t("start_btn", undefined, "mr")).toBe("सुरू करा");
    expect(t("fail_dropped", undefined, "mr")).toBe("जोडणी तुटली, पुन्हा बोला दाबा");
  });

  it("fills placeholders and follows the current language", () => {
    setElderLang("ta");
    expect(getElderLang()).toBe("ta");
    expect(t("talk_to", { name: "Arjun" })).toContain("Arjun");
    expect(t("speak")).toBe(t("speak", undefined, "ta"));
    setElderLang("zz");
    expect(getElderLang()).toBe("mr"); // unknown language -> Marathi default
  });

  it("language helpers know all ten and fall back to English for the rest", () => {
    for (const l of ELDER_LANGUAGES) expect(elderLanguage(l)).toBe(l);
    expect(elderLanguage("or")).toBe("en");
    expect(orbLabel("te", "listening")).not.toBe(orbLabel("en", "listening"));
    expect(timeGreeting("ta", 9)).toBe("காலை வணக்கம்");
  });

  it("date and time words follow the language, Marathi digits only in Marathi", () => {
    const d = new Date(2026, 10, 9, 15, 30); // Monday 9 Nov 2026, 15:30
    setElderLang("mr");
    expect(spokenTime("15:00")).toBe("दुपारी ३ वाजता");
    expect(timeLabel("10:00")).toBe("सकाळी १०:००");
    expect(dayWord(d, d)).toBe("आज");
    expect(weekday(d)).toBe("सोमवार");
    setElderLang("ta");
    expect(spokenTime("15:00")).toBe("மதியம் 3 மணிக்கு");
    expect(spokenTime("16:00")).toBe("மாலை 4 மணிக்கு");
    expect(dayWord(d, d)).toBe("இன்று");
    expect(weekday(d)).toBe("திங்கள்");
    expect(dateLine(d)).toBe("திங்கள், 9 நவம்பர்");
    expect(periodOfDay(9)).toBe("காலை");
    setElderLang("en");
    expect(spokenTime("15:00")).toBe("afternoon 3");
  });
});

describe("a spoken language switch drives the labels", () => {
  it("the active switch wins over the profile language, else the profile, else Marathi", () => {
    expect(uiLanguage("hi", "mr")).toBe("hi");
    expect(uiLanguage("", "ta")).toBe("ta");
    expect(uiLanguage(undefined, undefined)).toBe("mr");
    expect(uiLanguage("xx", "en")).toBe("en"); // an unknown tag is ignored
  });
  it("the labels really change with it (no Marathi/Hindi mix)", () => {
    setElderLang(uiLanguage("hi", "mr"));
    expect(t("speak")).toBe("बोलिए");
    expect(t("help")).toBe("मदद");
    setElderLang(uiLanguage("", "mr"));
    expect(t("speak")).toBe("बोला");
  });
});
