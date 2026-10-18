import type { StatusFilter } from "../../lib/review";

const CHIPS: { key: StatusFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "needs_attention", label: "Needs attention" },
  { key: "ready", label: "Ready" },
  { key: "verified", label: "Verified" },
  { key: "sent", label: "Sent" },
];

/** Status filter chips for the selected colleague's meetings, each with its count. */
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
        const alert = key === "needs_attention" && count > 0 && !on;
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
              className={`tabular font-heading font-bold ${on ? "text-beige" : alert ? "text-red" : count === 0 ? "text-muted" : "text-ink"}`}
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
