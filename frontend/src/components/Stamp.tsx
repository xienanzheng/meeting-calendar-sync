import { Check } from "lucide-react";
import type { Meeting } from "../api";
import { stampFor, type StampTone } from "../lib/review";

// Tilted, letter-spaced stamps; DRAFT and CANCELLED lie flat.
const TONES: Record<StampTone, string> = {
  navy: "-rotate-3 border-navy text-navy",
  green: "-rotate-3 border-green text-green",
  red: "-rotate-3 border-red text-red",
  amber: "-rotate-3 border-amber text-amber",
  muted: "border-stamp text-muted",
  struck: "border-stamp text-muted line-through decoration-[1.5px]",
};

/** A stamp for any label and tone; `Stamp` picks both from a meeting. */
export function StampMark({ label, tone }: { label: string; tone: StampTone }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-[4px] border-[1.5px] px-2 py-1 font-heading text-[11px] font-bold leading-none tracking-[0.1em] ${TONES[tone]}`}
    >
      {tone === "green" && <Check className="size-3" strokeWidth={3} aria-hidden="true" />}
      {label}
    </span>
  );
}

export function Stamp({ meeting }: { meeting: Meeting }) {
  return <StampMark {...stampFor(meeting)} />;
}
