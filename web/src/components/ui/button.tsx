import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-3 whitespace-nowrap rounded-lg font-semibold transition-colors " +
    "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring focus-visible:ring-offset-2 " +
    "disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-6 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-[var(--primary-hover)]",
        secondary: "border border-border bg-secondary text-secondary-foreground hover:bg-card",
        outline: "border-2 border-input bg-background text-foreground hover:bg-secondary",
        ghost: "text-foreground hover:bg-secondary",
        /** Emergency screen ONLY: red is not used anywhere else. */
        emergency: "bg-emergency text-emergency-foreground hover:opacity-90",
      },
      size: {
        default: "min-h-touch min-w-touch px-6 text-xl",
        lg: "min-h-[72px] min-w-touch px-8 text-2xl",
        icon: "size-touch",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export type ButtonProps = ButtonPrimitive.Props & VariantProps<typeof buttonVariants>;

/** shadcn Button (base-nova): the Base UI button primitive with this app's variants and 56 px touch targets. */
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, ...props }, ref) => (
  <ButtonPrimitive ref={ref} data-slot="button" className={cn(buttonVariants({ variant, size }), className as string | undefined)} {...props} />
));
Button.displayName = "Button";
