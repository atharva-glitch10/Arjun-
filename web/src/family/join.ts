/** The family-call link: `?view=join&t=<signed token>`. Pure helpers, so the page logic is testable. */

export function joinTokenFrom(search: string): string {
  return new URLSearchParams(search).get("t")?.trim() ?? "";
}

/** core-api errors arrive as "403: join link is invalid or expired" (see api.ts). */
export function statusFromError(error: unknown): number {
  const message = error instanceof Error ? error.message : "";
  const code = Number(message.split(":", 1)[0]);
  return Number.isFinite(code) ? code : 0;
}

export function joinProblem(status: number): string {
  if (status === 403) return "ही लिंक कालबुध्द झाली आहे. नवीन लिंकसाठी घरच्यांना सांगा.";
  if (status === 409) return "आई सध्या ॲपवर नाहीत";
  if (status === 503) return "आवाज सेवा सध्या उपलब्ध नाही. थोड्या वेळाने पुन्हा प्रयत्न करा.";
  return "लिंक उघडता आली नाही. पुन्हा प्रयत्न करा.";
}
