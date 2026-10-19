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
    const below = window.innerHeight - rect.bottom - 24;
    const above = rect.top - 24;
    // Once open, the panel has a real height. If it doesn't fit below and there's more room above (a field
    // low in the source panel), it opens upward, sliding over its trigger rather than off-screen, so the
    // heading and the buttons both stay in view.
    panel.style.maxHeight = "none";
    const natural = panel.matches(":popover-open") ? panel.scrollHeight : 0;
    if (natural > below && above > below) {
      const height = Math.min(natural, window.innerHeight - 16);
      panel.style.top = `${Math.max(8, rect.top - 8 - height)}px`;
      panel.style.maxHeight = `${height}px`;
    } else {
      panel.style.top = `${rect.bottom + 8}px`;
      panel.style.maxHeight = `${Math.max(160, below)}px`;
    }
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
      onToggle={(event) => {
        const open = event.newState === "open";
        onOpenChange?.(open);
        if (open) requestAnimationFrame(place); // measure with the content rendered
      }}
      // Reset what the trigger's surroundings pass down (the bar's nowrap, small text, white ink).
      className="popover-panel overflow-y-auto whitespace-normal rounded-lg border border-line bg-white p-0 text-left text-sm font-normal normal-case tracking-normal text-ink shadow-[0_8px_24px_rgba(24,41,88,0.18)]"
    >
      {children}
    </div>
  );
}
