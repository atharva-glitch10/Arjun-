import {
  MessageScroller as MessageScrollerPrimitive,
  useMessageScroller,
  useMessageScrollerScrollable,
  useMessageScrollerVisibility,
} from "@shadcn/react/message-scroller";
import { ArrowDownIcon } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

import { Button } from "./button";

// shadcn Message Scroller (base-nova) over the headless @shadcn/react primitive, Tailwind v3 spelling.
// NOTE: @shadcn/react declares react >= 19 as an (optional) peer; this app is on React 18.3. It was installed with
// --legacy-peer-deps and its `ref`-as-prop is never used by our callers. Verified in the browser, not by the peer range.
export function MessageScrollerProvider(props: ComponentProps<typeof MessageScrollerPrimitive.Provider>) {
  return <MessageScrollerPrimitive.Provider {...props} />;
}

export function MessageScroller({ className, ...props }: ComponentProps<typeof MessageScrollerPrimitive.Root>) {
  return (
    <MessageScrollerPrimitive.Root
      data-slot="message-scroller"
      className={cn("group/message-scroller relative flex size-full min-h-0 flex-col overflow-hidden", className)}
      {...props}
    />
  );
}

export function MessageScrollerViewport({ className, ...props }: ComponentProps<typeof MessageScrollerPrimitive.Viewport>) {
  return (
    <MessageScrollerPrimitive.Viewport
      data-slot="message-scroller-viewport"
      className={cn("size-full min-h-0 min-w-0 overflow-y-auto overscroll-contain data-[pending-scroll]:invisible", className)}
      {...props}
    />
  );
}

export function MessageScrollerContent({ className, ...props }: ComponentProps<typeof MessageScrollerPrimitive.Content>) {
  return <MessageScrollerPrimitive.Content data-slot="message-scroller-content" className={cn("flex h-max min-h-full flex-col gap-4", className)} {...props} />;
}

export function MessageScrollerItem({ className, scrollAnchor = false, ...props }: ComponentProps<typeof MessageScrollerPrimitive.Item>) {
  return (
    <MessageScrollerPrimitive.Item
      data-slot="message-scroller-item"
      scrollAnchor={scrollAnchor}
      className={cn("min-w-0 shrink-0", className)}
      {...props}
    />
  );
}

export function MessageScrollerButton({
  direction = "end",
  className,
  children,
  render,
  variant = "secondary",
  size = "icon",
  ...props
}: ComponentProps<typeof MessageScrollerPrimitive.Button> & Pick<ComponentProps<typeof Button>, "variant" | "size">) {
  return (
    <MessageScrollerPrimitive.Button
      data-slot="message-scroller-button"
      data-direction={direction}
      direction={direction}
      className={cn(
        "absolute start-1/2 -translate-x-1/2 border border-border bg-background text-foreground shadow-card transition-[transform,opacity] duration-200",
        "data-[active=false]:pointer-events-none data-[active=false]:scale-95 data-[active=false]:opacity-0 data-[active=true]:scale-100 data-[active=true]:opacity-100",
        "data-[direction=end]:bottom-3 data-[direction=start]:top-3 data-[direction=start]:[&_svg]:rotate-180",
        className,
      )}
      // React 18: the primitive passes `inert` as a boolean (React 19 style), which React 18 renders as inert="false" (= still inert).
      // A real attribute is "" when inert and absent when not.
      render={render ?? ((buttonProps, state) => <Button {...(buttonProps as object)} {...({ inert: state.active ? undefined : "" } as object)} variant={variant} size={size} />)}
      {...props}
    >
      {children ?? (
        <>
          <ArrowDownIcon aria-hidden />
          <span className="sr-only">{direction === "end" ? "Scroll to end" : "Scroll to start"}</span>
        </>
      )}
    </MessageScrollerPrimitive.Button>
  );
}

export { useMessageScroller, useMessageScrollerScrollable, useMessageScrollerVisibility };
