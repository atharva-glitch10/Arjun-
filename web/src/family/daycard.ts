/** The family's "आजचा दिवस" card: each proactive check-in as ✅ / ❌ / — with its time. Pure, so it is tested.
 *
 * Only what happened, never her words (the server sends none) and never a mood or score (those stay behind the
 * consent flag in the wellbeing card). "done" and "not done" are self-reported; "—" means Arjun asked and heard no
 * answer; a question still waiting for her answer shows "…"; one that was never asked (no voice session, a busy moment, a quiet hour) says so instead of
 * pretending it was asked.
 */

import type { CheckinCardItem } from "../api";

export interface DayCardRow {
  key: string;
  /** "नाश्ता", "औषध (Glimepiride)", "भेट (गायन वर्ग)" */
  title: string;
  mark: "✅" | "❌" | "—" | "…" | "○" | "·";
  /** HH:MM, the answer time when there is one, else the due time */
  time: string;
  /** Plain words for a screen reader and a tooltip. */
  words: string;
  /** "नाश्ता ✅ 08:40" as a single line (what the family would read in a message). */
  line: string;
}

const NAMES: Record<string, string> = {
  sleep: "झोप",
  breakfast: "नाश्ता",
  lunch: "दुपारचं जेवण",
  dinner: "रात्रीचं जेवण",
  walk: "फिरणं",
  interest: "आवड",
  home: "घर",
  medicine: "औषध",
  appointment: "भेट",
  reminder: "काम",
  bp: "बीपी",
};

type Mark = { mark: DayCardRow["mark"]; words: string };
const NOT_ASKED: Mark = { mark: "·", words: "not asked" };
const MARKS: Record<string, Mark> = {
  done: { mark: "✅", words: "done (self-reported)" },
  not_done: { mark: "❌", words: "not done (self-reported)" },
  no_answer: { mark: "—", words: "asked, no answer" },
  asking: { mark: "…", words: "asked, waiting for her answer" },
  waiting: { mark: "○", words: "later today" },
  not_asked: NOT_ASKED,
};

const hhmm = (iso: string) => iso.slice(11, 16);

export function dayCardRows(items: readonly CheckinCardItem[]): DayCardRow[] {
  return [...items]
    .sort((a, b) => a.at.localeCompare(b.at) || a.kind.localeCompare(b.kind))
    .map((i, n) => {
      const m = MARKS[i.state] ?? NOT_ASKED;
      const name = NAMES[i.kind] ?? i.kind;
      const title = i.label ? `${name} (${i.label})` : name;
      const time = hhmm(i.at);
      return { key: `${i.kind}-${n}`, title, mark: m.mark, time, words: m.words, line: `${title} ${m.mark} ${time}` };
    });
}

/** "2 of 3 answered": counts only the questions that were really asked. */
export function dayCardSummary(items: readonly CheckinCardItem[]): string {
  const asked = items.filter((i) => ["done", "not_done", "no_answer", "asking"].includes(i.state));
  if (asked.length === 0) return "Nothing asked yet today.";
  const answered = asked.filter((i) => i.state === "done" || i.state === "not_done").length;
  return `${answered} of ${asked.length} answered`;
}
