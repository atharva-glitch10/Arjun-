import { LoaderIcon } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/** shadcn Spinner. `motion-reduce` stops the spin (prefers-reduced-motion); the icon + the status text still say what is happening. */
export function Spinner({ className, ...props }: ComponentProps<"svg">) {
  return <LoaderIcon role="status" aria-label="Loading" className={cn("size-6 animate-spin motion-reduce:animate-none", className)} {...props} />;
}
