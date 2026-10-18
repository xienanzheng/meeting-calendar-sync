import type { StatusFilter } from "../../lib/review";

const CHIPS: { key: StatusFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "needs_attention", label: "Needs attention" },
  { key: "warnings", label: "Warnings" },
  { key: "ready", label: "Ready" },
  { key: "verified", label: "Verified" },
  { key: "sent", label: "Sent" },
];

// A count that asks for a look: red for what blocks verifying, amber for warnings worth checking.
const ALERT: Partial<Record<StatusFilter, string>> = { needs_attention: "text-red", warnings: "text-amber" };

/**
 * Status filter chips for the selected colleague's meetings, each with its count. "Warnings" cuts across
 * the states: every live meeting with a warning (a fuzzy match, a double booking, an assumed end…).
 */
export function StatusChips({
  counts,
  value,
  onChange,
}: {
  counts: Record<StatusFilter, number>;
  value: StatusFilter;
  onChange: (value: StatusFilter) => void;
}) {
  return (
    <div role="group" aria-label="Filter meetings by status" className="flex flex-wrap gap-2">
      {CHIPS.map(({ key, label }) => {
        const on = value === key;
        const count = counts[key];
        const alert = count > 0 && !on ? ALERT[key] : undefined;
        return (
          <button
            key={key}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(key)}
            className={[
              "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-semibold",
              "transition-colors duration-150 ease-out",
              on
                ? "border-navy-2 bg-navy-2 text-white"
                : "border-line bg-white text-ink hover:border-line-strong hover:bg-cream",
            ].join(" ")}
          >
            {label}
            <span
              className={`tabular font-heading font-bold ${on ? "text-beige" : (alert ?? (count === 0 ? "text-muted" : "text-ink"))}`}
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
