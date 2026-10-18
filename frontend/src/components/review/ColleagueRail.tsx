import { ChevronDown, Users } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import type { Severity } from "../../api";
import { initials } from "../../lib/format";
import { selectionFromKey, selectionKey, type ColleagueEntry, type Selection, type UnmatchedEntry } from "../../lib/review";
import { inputClass } from "../fields";

export interface RailProps {
  colleagues: ColleagueEntry[];
  unmatched: UnmatchedEntry[];
  total: number;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}

const FLAG_TEXT: Record<Severity, string> = { block: "needs attention", warn: "has warnings" };

function RailRow({
  selected,
  focusable,
  avatar,
  name,
  count,
  worst = null,
  onClick,
}: {
  selected: boolean;
  focusable: boolean;
  avatar: ReactNode;
  name: string;
  count: number;
  worst?: Severity | null;
  onClick: () => void;
}) {
  const dot = worst === "block" ? (selected ? "bg-red-on-navy" : "bg-red") : selected ? "bg-amber-on-navy" : "bg-amber";
  return (
    <li>
      <button
        type="button"
        data-rail-row
        tabIndex={focusable ? 0 : -1}
        aria-current={selected ? "true" : undefined}
        onClick={onClick}
        className={[
          "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm font-semibold",
          "transition-colors duration-150 ease-out",
          selected ? "bg-navy text-white" : "text-ink hover:bg-beige/45",
        ].join(" ")}
      >
        {avatar}
        <span className="min-w-0 flex-1 truncate">{name}</span>
        {worst && (
          <span className={`size-2 shrink-0 rounded-full ${dot}`}>
            <span className="sr-only">, {FLAG_TEXT[worst]}</span>
          </span>
        )}
        <span className={`tabular w-6 shrink-0 text-right font-heading ${selected ? "text-beige" : "text-muted"}`}>
          {count}
          <span className="sr-only"> {count === 1 ? "meeting" : "meetings"}</span>
        </span>
      </button>
    </li>
  );
}

function Avatar({ children, tone = "beige" }: { children: ReactNode; tone?: "beige" | "rose" }) {
  return (
    <span
      aria-hidden="true"
      className={`grid size-7 shrink-0 place-items-center rounded-full font-heading text-[11px] font-bold text-navy ${tone === "rose" ? "bg-red-line" : "bg-beige"}`}
    >
      {children}
    </span>
  );
}

const headingClass = "mx-2.5 mb-2 font-heading text-xs font-bold uppercase tracking-[0.1em] text-muted";

/**
 * The colleague rail: All, every colleague on this conference with a flag dot and count, then the
 * printed names not on the roster. Rows are buttons; Up/Down (and Home/End) move and select.
 */
export function ColleagueRail({ colleagues, unmatched, total, selection, onSelect }: RailProps) {
  const current = selectionKey(selection);
  const keys = ["all", ...colleagues.map((c) => `c:${c.id}`), ...unmatched.map((u) => `u:${u.name}`)];
  const tabStop = keys.includes(current) ? current : "all";

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const rows = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("[data-rail-row]"));
    const at = rows.indexOf(document.activeElement as HTMLButtonElement);
    if (at < 0) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? rows.length - 1
          : Math.min(rows.length - 1, Math.max(0, at + (event.key === "ArrowDown" ? 1 : -1)));
    rows[next].focus();
    rows[next].click();
  }

  return (
    <nav aria-label="Colleagues" onKeyDown={onKeyDown} className="px-3.5 py-5">
      <h2 className={headingClass}>Colleagues</h2>
      <ul className="space-y-0.5">
        <RailRow
          selected={current === "all"}
          focusable={tabStop === "all"}
          avatar={
            <Avatar>
              <Users className="size-3.5" strokeWidth={2.5} />
            </Avatar>
          }
          name="All colleagues"
          count={total}
          onClick={() => onSelect({ kind: "all" })}
        />
        {colleagues.map((c) => (
          <RailRow
            key={c.id}
            selected={current === `c:${c.id}`}
            focusable={tabStop === `c:${c.id}`}
            avatar={<Avatar>{initials(c.name)}</Avatar>}
            name={c.name}
            count={c.count}
            worst={c.worst}
            onClick={() => onSelect({ kind: "colleague", id: c.id })}
          />
        ))}
      </ul>
      {unmatched.length > 0 && (
        <>
          <h2 className={`${headingClass} mt-6`}>Not on roster</h2>
          <ul className="space-y-0.5">
            {unmatched.map((u) => (
              <RailRow
                key={u.name}
                selected={current === `u:${u.name}`}
                focusable={tabStop === `u:${u.name}`}
                avatar={<Avatar tone="rose">{initials(u.name)}</Avatar>}
                name={u.name}
                count={u.count}
                onClick={() => onSelect({ kind: "unmatched", name: u.name })}
              />
            ))}
          </ul>
        </>
      )}
    </nav>
  );
}

/** The rail as a select, above the chips on narrow windows. */
export function ColleagueSelect({ colleagues, unmatched, total, selection, onSelect }: RailProps) {
  const flag = (worst: Severity | null) => (worst ? ` — ${FLAG_TEXT[worst]}` : "");
  return (
    <label className="block">
      <span className="sr-only">Colleague</span>
      <span className="relative block">
        <select
          value={selectionKey(selection)}
          onChange={(event) => onSelect(selectionFromKey(event.target.value))}
          className={`${inputClass} h-10 appearance-none pr-9 font-semibold`}
        >
          <option value="all">All colleagues ({total})</option>
          {colleagues.map((c) => (
            <option key={c.id} value={`c:${c.id}`}>
              {c.name} ({c.count}){flag(c.worst)}
            </option>
          ))}
          {unmatched.length > 0 && (
            <optgroup label="Not on roster">
              {unmatched.map((u) => (
                <option key={u.name} value={`u:${u.name}`}>
                  {u.name} ({u.count})
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden="true" />
      </span>
    </label>
  );
}
