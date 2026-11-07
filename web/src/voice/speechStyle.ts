export interface SpeechStyle {
  rate: "normal" | "slow";
  volume: "normal" | "loud";
  simple: boolean;
}

export function playbackVolume(style: Pick<SpeechStyle, "volume">, saved: number): number {
  return style.volume === "loud" ? 1 : Math.min(1, Math.max(0.1, saved));
}
