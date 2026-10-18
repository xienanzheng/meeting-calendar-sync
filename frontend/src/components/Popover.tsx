import { useEffect, useRef, type ReactNode, type RefObject } from "react";

/**
 * A light-dismiss panel in the browser's top layer (the popover API), so it escapes the bar and every
 * scroll container. Opened by a button with `popoverTarget={id}`; placed under `anchor`, right-aligned.
 * Esc and an outside click close it; it is not a modal.
 */
export function Popover({
  id,
  anchor,
  label,
  width = 340,
  onOpenChange,
  children,
}: {
  id: string;
  anchor: RefObject<HTMLElement | null>;
  label: string;
  width?: number;
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);

  function place() {
    const trigger = anchor.current;
    const panel = ref.current;
    if (!trigger || !panel) return;
    const rect = trigger.getBoundingClientRect();
    const w = Math.min(width, window.innerWidth - 16);
    const left = Math.min(Math.max(8, rect.right - w), window.innerWidth - w - 8);
    panel.style.width = `${w}px`;
    panel.style.left = `${left}px`;
    panel.style.top = `${rect.bottom + 8}px`;
    panel.style.maxHeight = `${Math.max(160, window.innerHeight - rect.bottom - 24)}px`;
  }

  useEffect(() => {
    const hide = () => {
      if (ref.current?.matches(":popover-open")) ref.current.hidePopover();
    };
    window.addEventListener("resize", hide);
    return () => window.removeEventListener("resize", hide);
  }, []);

  return (
    <div
      ref={ref}
      id={id}
      popover="auto"
      role="dialog"
      aria-label={label}
      onBeforeToggle={(event) => {
        if (event.newState === "open") place();
      }}
      onToggle={(event) => onOpenChange?.(event.newState === "open")}
      // Reset what the trigger's surroundings pass down (the bar's nowrap, small text, white ink).
      className="popover-panel overflow-y-auto whitespace-normal rounded-lg border border-line bg-white p-0 text-left text-sm font-normal normal-case tracking-normal text-ink shadow-[0_8px_24px_rgba(24,41,88,0.18)]"
    >
      {children}
    </div>
  );
}
