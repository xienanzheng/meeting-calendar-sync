import { Check } from "lucide-react";
import { useState } from "react";
import type { Meeting } from "../api";
import { stampFor, type StampTone } from "../lib/review";

// Tilted, letter-spaced stamps; DRAFT and CANCELLED lie flat. Every stamp sits on a white chip so it keeps
// its contrast on the selected-row tint (green on #eef0f8 alone is only 4.5:1).
const TONES: Record<StampTone, string> = {
  navy: "-rotate-3 border-navy text-navy",
  green: "-rotate-3 border-green text-green",
  red: "-rotate-3 border-red text-red",
  amber: "-rotate-3 border-amber text-amber",
  muted: "border-stamp text-muted",
  struck: "border-stamp text-muted line-through decoration-[1.5px]",
};

/** A stamp for any label and tone; `Stamp` picks both from a meeting. `landing` plays the stamp-down. */
export function StampMark({ label, tone, landing = false }: { label: string; tone: StampTone; landing?: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-[4px] border-[1.5px] bg-white px-2 py-1 font-heading text-[11px] font-bold leading-none tracking-[0.1em] ${TONES[tone]} ${landing ? "stamp-land" : ""}`}
    >
      {tone === "green" && <Check className="size-3" strokeWidth={3} aria-hidden="true" />}
      {label}
    </span>
  );
}

// The states a click earns: verifying stamps, and the calendar send ticks.
const LANDS = new Set(["VERIFIED", "SENT"]);

/**
 * A meeting's stamp. When it turns VERIFIED or SENT while on screen, the new stamp lands (styles.css,
 * `.stamp-land`); stamps already in that state when the page loads lie still.
 */
export function Stamp({ meeting }: { meeting: Meeting }) {
  const stamp = stampFor(meeting);
  const [shown, setShown] = useState(stamp.label);
  const [landings, setLandings] = useState(0);
  if (shown !== stamp.label) {
    setShown(stamp.label);
    if (LANDS.has(stamp.label)) setLandings((n) => n + 1);
  }
  // A new key remounts the mark, so each landing replays the animation once.
  return <StampMark key={landings} {...stamp} landing={landings > 0 && LANDS.has(stamp.label)} />;
}
