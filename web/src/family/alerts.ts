/** Emergency alerts the family must not miss. Pure, so it is tested. */
export interface AlertNote {
  id: number;
  kind?: string;
  body?: string;
  created_at: string;
}

/** Emergency notifications from the last `hours` hours, newest first (yesterday's alert must not stay on screen). */
export function recentEmergencies<T extends AlertNote>(notes: T[], now: Date, hours = 24): T[] {
  const since = now.getTime() - hours * 3_600_000;
  return notes
    .filter((n) => n.kind === "emergency" && new Date(n.created_at).getTime() >= since)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}
