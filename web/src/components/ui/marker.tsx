import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

// shadcn Marker (base-nova), adapted to Tailwind v3: no `[a]:` element variants, elder-sized text.
export const markerVariants = cva(
  "group/marker relative flex min-h-4 w-full items-center gap-2 text-left text-lg text-muted-foreground [&_svg:not([class*='size-'])]:size-5",
  {
    variants: {
      variant: {
        default: "",
        separator:
          "before:mr-1 before:h-px before:min-w-0 before:flex-1 before:bg-border after:ml-1 after:h-px after:min-w-0 after:flex-1 after:bg-border",
        border: "border-b border-border pb-2",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Marker({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"div"> & VariantProps<typeof markerVariants>) {
  return useRender({
    defaultTagName: "div",
    props: mergeProps<"div">({ className: cn(markerVariants({ variant, className })) }, props),
    render,
    state: { slot: "marker", variant },
  });
}

export function MarkerIcon({ className, ...props }: ComponentProps<"span">) {
  return <span data-slot="marker-icon" aria-hidden="true" className={cn("size-5 shrink-0", className)} {...props} />;
}

export function MarkerContent({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      data-slot="marker-content"
      className={cn("min-w-0 break-words group-data-[variant=separator]/marker:flex-none group-data-[variant=separator]/marker:text-center", className)}
      {...props}
    />
  );
}
