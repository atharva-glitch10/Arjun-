import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

// shadcn Bubble (base-nova), adapted to Tailwind v3 and the Arjun tokens: elder text size (>= 24 px), no opacity-suffix colours.
export function BubbleGroup({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="bubble-group" className={cn("flex min-w-0 flex-col gap-2", className)} {...props} />;
}

export const bubbleVariants = cva(
  "group/bubble relative flex w-fit max-w-[86%] min-w-0 flex-col gap-1 group-data-[align=end]/message:self-end data-[align=end]:self-end data-[variant=ghost]:max-w-full",
  {
    variants: {
      variant: {
        /** Her words: amber (primary) with navy text. */
        default: "[&>[data-slot=bubble-content]]:bg-primary [&>[data-slot=bubble-content]]:text-primary-foreground",
        secondary: "[&>[data-slot=bubble-content]]:bg-secondary [&>[data-slot=bubble-content]]:text-secondary-foreground",
        muted: "[&>[data-slot=bubble-content]]:bg-muted [&>[data-slot=bubble-content]]:text-foreground",
        tinted: "[&>[data-slot=bubble-content]]:bg-secondary [&>[data-slot=bubble-content]]:text-foreground",
        /** Arjun's words: white with a visible border. */
        outline: "[&>[data-slot=bubble-content]]:border-border [&>[data-slot=bubble-content]]:bg-background [&>[data-slot=bubble-content]]:text-foreground",
        ghost: "border-none [&>[data-slot=bubble-content]]:rounded-none [&>[data-slot=bubble-content]]:bg-transparent [&>[data-slot=bubble-content]]:p-0",
        destructive: "[&>[data-slot=bubble-content]]:bg-emergency [&>[data-slot=bubble-content]]:text-emergency-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Bubble({
  variant = "default",
  align = "start",
  className,
  ...props
}: ComponentProps<"div"> & VariantProps<typeof bubbleVariants> & { align?: "start" | "end" }) {
  return <div data-slot="bubble" data-variant={variant} data-align={align} className={cn(bubbleVariants({ variant }), className)} {...props} />;
}

export function BubbleContent({ className, render, ...props }: useRender.ComponentProps<"div">) {
  return useRender({
    defaultTagName: "div",
    props: mergeProps<"div">(
      {
        className: cn(
          "w-fit max-w-full min-w-0 overflow-hidden rounded-lg border border-transparent px-4 py-3 text-2xl leading-relaxed break-words group-data-[align=end]/bubble:self-end",
          className,
        ),
      },
      props,
    ),
    render,
    state: { slot: "bubble-content" },
  });
}
