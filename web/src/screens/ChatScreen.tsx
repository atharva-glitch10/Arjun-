import { Check, Info, Volume2, X } from "lucide-react";
import type { ReactNode } from "react";

import { Orb } from "@/components/Orb";
import type { OrbState } from "@/components/orbState";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker";
import { Message, MessageContent, MessageFooter } from "@/components/ui/message";
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import { Spinner } from "@/components/ui/spinner";

export interface ChatMsg {
  id: number;
  who: "me" | "arjun";
  text: string;
  /** "HH:MM" under the bubble. */
  time: string;
}

/** What the conversation is doing right now. It drives the one status line under the messages and the header orb. */
export type ChatStatus = "idle" | "connecting" | "recording" | "sending" | "thinking" | "speaking";

const ORB: Record<ChatStatus, OrbState> = {
  idle: "idle",
  connecting: "connecting",
  recording: "listening",
  sending: "thinking",
  thinking: "thinking",
  speaking: "speaking",
};

/** One status line: a spinner while Arjun is connecting / sending / thinking, a speaker icon while he is talking. Nothing when idle. */
function StatusMarker({ status, label }: { status: ChatStatus; label: string }) {
  if (!label || status === "idle" || status === "recording") return null;
  return (
    <Marker role="status" aria-live="polite" className="text-foreground">
      <MarkerIcon>{status === "speaking" ? <Volume2 /> : <Spinner aria-hidden />}</MarkerIcon>
      <MarkerContent>{label}</MarkerContent>
    </Marker>
  );
}

/** Her words on the right (amber), Arjun's on the left (white), newest at the bottom, scroll follows the conversation. The
 *  sentence she is still saying (hands-free) shows as a faded bubble. */
export function ChatMessages({
  messages,
  live,
  status = "idle",
  statusLabel = "",
  emptyText = "",
  scrollLabel,
}: {
  messages: ChatMsg[];
  live?: string;
  status?: ChatStatus;
  statusLabel?: string;
  emptyText?: string;
  scrollLabel?: string;
}) {
  const busy = status === "thinking" || status === "sending";
  return (
    <MessageScrollerProvider autoScroll defaultScrollPosition="end">
      <MessageScroller className="min-h-[220px] flex-1">
        <MessageScrollerViewport aria-label={scrollLabel}>
          <MessageScrollerContent className="px-1 py-3" aria-busy={busy || undefined}>
            {messages.length === 0 && !live && emptyText && (
              <MessageScrollerItem>
                <Marker variant="separator" className="text-2xl leading-relaxed text-foreground">
                  <MarkerContent>{emptyText}</MarkerContent>
                </Marker>
              </MessageScrollerItem>
            )}
            {messages.map((m) => (
              <MessageScrollerItem key={m.id} messageId={String(m.id)}>
                <Message align={m.who === "me" ? "end" : "start"}>
                  <MessageContent>
                    <Bubble align={m.who === "me" ? "end" : "start"} variant={m.who === "me" ? "default" : "outline"}>
                      <BubbleContent>{m.text}</BubbleContent>
                    </Bubble>
                    <MessageFooter>{m.time}</MessageFooter>
                  </MessageContent>
                </Message>
              </MessageScrollerItem>
            ))}
            {live && (
              <MessageScrollerItem>
                <Message align="end">
                  <MessageContent>
                    <Bubble align="end" variant="muted">
                      <BubbleContent>{live} …</BubbleContent>
                    </Bubble>
                  </MessageContent>
                </Message>
              </MessageScrollerItem>
            )}
            <MessageScrollerItem>
              <StatusMarker status={status} label={statusLabel} />
            </MessageScrollerItem>
          </MessageScrollerContent>
        </MessageScrollerViewport>
        <MessageScrollerButton />
      </MessageScroller>
    </MessageScrollerProvider>
  );
}

/** The whole /chat screen: header (name + orb), the conversation, then ONE control at the bottom: yes / no while Arjun waits for an
 *  answer, otherwise the record button (`footer`). No Stop / OK / Back buttons: the conversation never needs them. */
export function ChatScreen(p: {
  title: string;
  disclosure: string;
  messages: ChatMsg[];
  live?: string;
  status: ChatStatus;
  statusLabel: string;
  orbLabel: string;
  emptyText: string;
  scrollLabel?: string;
  error?: string;
  /** Arjun asked something that needs a yes / no. Replaces the record button until it is answered. */
  ask?: { yesLabel: string; noLabel: string; busy: boolean; onYes: () => void; onNo: () => void };
  footer: ReactNode;
}) {
  return (
    <div className="screen ui-root !h-[100dvh] !min-h-0 gap-3 !pb-4">
      <header className="flex items-center gap-4">
        <Orb state={ORB[p.status]} label={p.orbLabel} size="4rem" />
        <h1 className="m-0 text-[28px] font-bold leading-tight text-foreground">{p.title}</h1>
      </header>
      <ChatMessages
        messages={p.messages}
        live={p.live}
        status={p.status}
        statusLabel={p.statusLabel}
        emptyText={p.emptyText}
        scrollLabel={p.scrollLabel}
      />
      {p.error && (
        <Marker role="alert" className="text-foreground">
          <MarkerIcon>
            <Info />
          </MarkerIcon>
          <MarkerContent>{p.error}</MarkerContent>
        </Marker>
      )}
      <div className="flex flex-col gap-3">
        {p.ask ? (
          <div className="flex gap-3" role="group">
            <Button size="lg" className="flex-1" disabled={p.ask.busy} onClick={p.ask.onYes}>
              <Check aria-hidden /> {p.ask.yesLabel}
            </Button>
            <Button size="lg" variant="secondary" className="flex-1" disabled={p.ask.busy} onClick={p.ask.onNo}>
              <X aria-hidden /> {p.ask.noLabel}
            </Button>
          </div>
        ) : (
          p.footer
        )}
        <p className="m-0 text-center text-base text-muted-foreground">{p.disclosure}</p>
      </div>
    </div>
  );
}
