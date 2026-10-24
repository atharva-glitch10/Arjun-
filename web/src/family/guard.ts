/** Ask before a click that is easy to regret (e.g. creating a second demo user). `ask` is window.confirm. */
export async function confirmThen<T>(
  ask: (message: string) => boolean,
  message: string,
  action: () => Promise<T>,
): Promise<T | undefined> {
  if (!ask(message)) return undefined;
  return action();
}
