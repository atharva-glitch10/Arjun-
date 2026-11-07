const STOP_PHRASES = ["बंद कर", "बंद करा", "बंद कर ना", "थांब", "थांबव", "stop", "end call"];

export const isVideoCallStopCommand = (text: string): boolean => {
  const normalized = text.toLocaleLowerCase().replace(/[.,!?]/g, " ").replace(/\s+/g, " ").trim();
  return STOP_PHRASES.some((phrase) => normalized === phrase || normalized.startsWith(`${phrase} `));
};
