import * as React from "react";

import { cn } from "@/lib/utils";

import type { OrbState } from "./orbState";

export interface OrbProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "children"> {
  state: OrbState;
  /** Words for the current state (use `orbLabel` from elder/i18n). Read out by screen readers. */
  label: string;
  /** CSS length, e.g. "16rem". Defaults to the .orb size. */
  size?: string;
}

/** The amber orb. Motion comes from CSS keyframes on data-state and stops under prefers-reduced-motion / .no-motion. */
export function Orb({ state, label, size, className, style, ...rest }: OrbProps) {
  return (
    <div
      role="img"
      aria-label={label}
      data-state={state}
      className={cn("orb", className)}
      style={size ? ({ ...style, "--orb-size": size } as React.CSSProperties) : style}
      {...rest}
    />
  );
}
