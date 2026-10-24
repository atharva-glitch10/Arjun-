/** Keep the family dashboard fresh without ever blanking it.
 *
 * Refresh every `ms` while the tab is visible, at once when it becomes visible again, and when the window
 * gets focus. Never two refreshes at a time, and a failing refresh never stops the polling.
 */
export interface Listenable {
  addEventListener(type: string, fn: () => void): void;
  removeEventListener(type: string, fn: () => void): void;
  hidden?: boolean;
}

export function startPolling(
  refresh: () => Promise<void>,
  ms: number,
  doc: Listenable,
  win: Listenable,
): () => void {
  let inFlight = false;
  const run = () => {
    if (inFlight) return;
    inFlight = true;
    void refresh()
      .catch(() => {})
      .finally(() => {
        inFlight = false;
      });
  };
  const timer = setInterval(() => {
    if (!doc.hidden) run();
  }, ms);
  const onVisible = () => {
    if (!doc.hidden) run();
  };
  doc.addEventListener("visibilitychange", onVisible);
  win.addEventListener("focus", run);
  return () => {
    clearInterval(timer);
    doc.removeEventListener("visibilitychange", onVisible);
    win.removeEventListener("focus", run);
  };
}
