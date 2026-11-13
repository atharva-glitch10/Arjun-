import { Info, Mic, RotateCcw, Square, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker";
import { Spinner } from "@/components/ui/spinner";

import type { PushToRecord } from "../voice/usePushToRecord";
import { t } from "./strings";

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

const HINT = { too_short: "rec_too_short", empty: "rec_empty", error: "rec_sending", mic: "rec_mic" } as const;

/** The ONE control of /chat: tap to record, the same button becomes Stop (send) while recording, and is off while Arjun is
 *  sending / thinking / speaking (the status line above says which). Rendered inside the chat screen's footer. */
export function RecorderBar({ rec, ready, failed, onConnect }: { rec: PushToRecord; ready: boolean; failed?: boolean; onConnect: () => void }) {
  const [requested, setRequested] = useState(false);
  const [starting, setStarting] = useState(false);
  useEffect(() => {
    if (!requested) return;
    if (failed) { setRequested(false); return; }
    if (!ready) return;
    setRequested(false);
    setStarting(true);
    void rec.begin().finally(() => setStarting(false));
  }, [requested, ready, failed, rec.begin]);
  const busy = rec.state !== "idle" || requested || starting;
  const connecting = requested && !ready;
  return (
    <div className="flex w-full flex-col gap-3" role="group">
      {rec.hint && (
        <Marker role="alert" aria-live="polite" className="flex-wrap text-foreground">
          <MarkerIcon>{rec.hint === "error" ? <TriangleAlert /> : <Info />}</MarkerIcon>
          <MarkerContent>{rec.hint === "error" ? t("rec_empty") : t(HINT[rec.hint])}</MarkerContent>
          {rec.canRetry && (
            <Button variant="secondary" onClick={rec.retry}>
              <RotateCcw aria-hidden /> {t("rec_retry")}
            </Button>
          )}
        </Marker>
      )}
      {rec.state === "recording" ? (
        <>
          <div className="flex items-center gap-3 text-xl text-foreground" role="status">
            <span className="size-3.5 shrink-0 animate-pulse rounded-full bg-primary motion-reduce:animate-none" aria-hidden="true" />
            <span className="font-bold">{t("rec_recording")}…</span>
            <span className="ms-auto tabular-nums" aria-label={`${Math.floor(rec.seconds)} seconds`}>{mmss(rec.seconds)} / 0:30</span>
          </div>
          <div
            className="h-2.5 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-label={t("rec_recording")}
            aria-valuemin={0}
            aria-valuemax={30}
            aria-valuenow={Math.min(30, Math.floor(rec.seconds))}
          >
            <span className="block h-full bg-primary transition-[width] duration-200" style={{ width: `${Math.min(100, (rec.seconds / 30) * 100)}%` }} />
          </div>
          <Button size="lg" className="w-full" onClick={rec.send}>
            <Square aria-hidden /> {t("stop")}
          </Button>
        </>
      ) : (
        <Button
          size="lg"
          className="w-full"
          disabled={busy}
          onClick={() => {
            if (ready) {
              setStarting(true);
              void rec.begin().finally(() => setStarting(false));
            } else {
              setRequested(true);
              onConnect();
            }
          }}
        >
          {connecting || rec.state === "sending" ? <Spinner aria-hidden /> : <Mic aria-hidden />}
          {rec.state === "sending" ? t("rec_sending") : t("speak")}
        </Button>
      )}
    </div>
  );
}
