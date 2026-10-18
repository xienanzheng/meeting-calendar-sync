import { Loader2 } from "lucide-react";
import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from "react";

export type ButtonVariant = "primary" | "beige" | "quiet" | "danger";
export type ButtonSize = "md" | "sm" | "icon";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a spinner, disables the button and marks it busy without fading it. */
  loading?: boolean;
  /** A lucide icon shown before the label; replaced by the spinner while loading. */
  icon?: ReactNode;
}

const VARIANTS: Record<ButtonVariant, string> = {
  // navy fill, white text
  primary: "bg-navy text-white enabled:hover:bg-navy-2 enabled:active:bg-navy-3",
  // beige fill, navy text; sits on the navy bar, so its focus ring is beige
  beige: "bg-beige text-navy enabled:hover:bg-beige-2 enabled:active:bg-beige-3 focus-visible:outline-beige",
  // white with a hairline border
  quiet: "border border-line bg-white text-ink enabled:hover:border-line-strong enabled:hover:bg-cream enabled:active:bg-cream-2",
  // red text on white; fills a faint red on hover
  danger:
    "border border-red-line bg-white text-red enabled:hover:border-red enabled:hover:bg-red-bg enabled:active:bg-[#f9e2e5] focus-visible:outline-red",
};

const SIZES: Record<ButtonSize, string> = {
  md: "h-10 gap-2 px-4 text-sm",
  sm: "h-8 gap-1.5 px-3 text-[13px]",
  icon: "size-8",
};

export function Button({
  variant = "quiet",
  size = "md",
  loading = false,
  icon,
  disabled,
  className = "",
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={[
        "inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap rounded-md font-heading font-bold",
        "transition-colors duration-150 ease-out",
        loading ? "cursor-progress" : "disabled:cursor-not-allowed disabled:opacity-50",
        SIZES[size],
        VARIANTS[variant],
        className,
      ].join(" ")}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
}

export interface ConfirmButtonProps extends Omit<ButtonProps, "onClick" | "variant" | "children"> {
  onConfirm: () => void;
  label?: string;
  confirmLabel?: string;
  /** What is being deleted, read to screen readers after the label (e.g. the conference name). */
  subject?: string;
}

/**
 * A two-step destructive button with no modal: the first press turns it into "Delete for good?"
 * for four seconds; a second press within that time confirms.
 */
export function ConfirmButton({
  onConfirm,
  label = "Delete",
  confirmLabel = "Delete for good?",
  subject,
  ...rest
}: ConfirmButtonProps) {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!armed) return;
    const timer = window.setTimeout(() => setArmed(false), 4000);
    return () => window.clearTimeout(timer);
  }, [armed]);

  return (
    <>
      <Button
        {...rest}
        variant={armed ? "danger" : "quiet"}
        onClick={(event) => {
          event.stopPropagation();
          if (armed) {
            setArmed(false);
            onConfirm();
          } else {
            setArmed(true);
          }
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape" && armed) {
            event.stopPropagation();
            setArmed(false);
          }
        }}
      >
        {armed ? confirmLabel : label}
        {subject && <span className="sr-only"> {subject}</span>}
      </Button>
      <span className="sr-only" aria-live="polite">
        {armed ? "Press again within 4 seconds to delete." : ""}
      </span>
    </>
  );
}
