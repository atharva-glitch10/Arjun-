import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

// shadcn Message (base-nova), Tailwind v3 spelling of the `has-data` / `group-has` variants.
export function MessageGroup({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="message-group" className={cn("flex min-w-0 flex-col gap-2", className)} {...props} />;
}

export function Message({ className, align = "start", ...props }: ComponentProps<"div"> & { align?: "start" | "end" }) {
  return (
    <div
      data-slot="message"
      data-align={align}
      className={cn("group/message relative flex w-full min-w-0 gap-2 text-lg data-[align=end]:flex-row-reverse", className)}
      {...props}
    />
  );
}

export function MessageAvatar({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="message-avatar"
      className={cn("flex w-fit min-w-10 shrink-0 items-center justify-center self-end overflow-hidden rounded-full bg-muted", className)}
      {...props}
    />
  );
}

export function MessageContent({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="message-content"
      className={cn("flex w-full min-w-0 flex-col gap-1.5 break-words group-data-[align=end]/message:[&>[data-slot]]:self-end", className)}
      {...props}
    />
  );
}

export function MessageHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div data-slot="message-header" className={cn("flex max-w-full min-w-0 items-center px-3 text-base font-medium text-muted-foreground", className)} {...props} />
  );
}

export function MessageFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="message-footer"
      className={cn("flex max-w-full min-w-0 items-center px-3 text-base font-medium text-muted-foreground group-data-[align=end]/message:justify-end", className)}
      {...props}
    />
  );
}
