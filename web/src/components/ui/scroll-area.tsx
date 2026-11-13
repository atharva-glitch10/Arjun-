import { ScrollArea as ScrollAreaPrimitive } from "@base-ui/react/scroll-area";

import { cn } from "@/lib/utils";

/** shadcn ScrollArea (base-nova) on the Base UI primitive. */
export function ScrollBar({ className, orientation = "vertical", ...props }: ScrollAreaPrimitive.Scrollbar.Props) {
  return (
    <ScrollAreaPrimitive.Scrollbar
      data-slot="scroll-area-scrollbar"
      orientation={orientation}
      className={cn(
        "flex touch-none select-none p-0.5 transition-colors",
        orientation === "vertical" ? "h-full w-3 border-l border-l-transparent" : "h-3 flex-col border-t border-t-transparent",
        className as string | undefined,
      )}
      {...props}
    >
      <ScrollAreaPrimitive.Thumb data-slot="scroll-area-thumb" className="relative flex-1 rounded-full bg-input" />
    </ScrollAreaPrimitive.Scrollbar>
  );
}

export function ScrollArea({ className, children, ...props }: ScrollAreaPrimitive.Root.Props) {
  return (
    <ScrollAreaPrimitive.Root data-slot="scroll-area" className={cn("relative overflow-hidden", className as string | undefined)} {...props}>
      <ScrollAreaPrimitive.Viewport data-slot="scroll-area-viewport" className="size-full rounded-[inherit] outline-none focus-visible:ring-4 focus-visible:ring-ring">
        {children}
      </ScrollAreaPrimitive.Viewport>
      <ScrollBar />
      <ScrollAreaPrimitive.Corner />
    </ScrollAreaPrimitive.Root>
  );
}
