import { TriangleAlert } from "lucide-react";
import { useEffect, useRef, type KeyboardEvent } from "react";
import type { Meeting } from "../../api";
import { dayHeading, formatLabel, formatTime12, localHint } from "../../lib/format";
import { sharedWith, type DayGroup, type Selection } from "../../lib/review";
import { Stamp } from "../Stamp";

export type SelectVia = "pointer" | "keyboard";

// Keep a clock time and its AM/PM on one line; the pieces may still wrap at the separators.
const keepTime = (text: string) => text.replace(/(\d) (AM|PM)/g, "$1 $2");

const cell = "border-b border-rule px-3 py-[11px] align-middle";

function TimeCell({ meeting, hotelTz, viewerTz }: { meeting: Meeting; hotelTz: string | null; viewerTz: string }) {
  const hint = localHint(meeting.date, meeting.start, hotelTz, viewerTz);
  const struck = meeting.review_state === "cancelled" ? "line-through decoration-[1.5px]" : "";
  const detail = meeting.start
    ? [`to ${keepTime(formatTime12(meeting.end))}${meeting.end_assumed ? " (assumed)" : ""}`, hint && keepTime(hint)]
        .filter(Boolean)
        .join(" · ")
    : "time missing";
  return (
    <td className={`tt-time ${cell}`}>
      <span className={`tabular block font-heading text-sm font-bold ${struck}`}>{formatTime12(meeting.start)}</span>
      <span className="block text-xs font-medium leading-snug text-muted">{detail}</span>
    </td>
  );
}

function StatusCell({ meeting }: { meeting: Meeting }) {
  const blocks = meeting.flags.filter((f) => f.severity === "block");
  const warns = meeting.flags.filter((f) => f.severity === "warn");
  const warnText = warns.map((f) => f.message).join("\n");
  return (
    <td className={`tt-status ${cell}`}>
      <span className="inline-flex flex-wrap items-center gap-1.5">
        {/* Long stamps (NEEDS COLLEAGUE) break onto two lines rather than overflow the 8rem column. */}
        <span
          title={blocks.length > 1 ? blocks.map((f) => f.message).join("\n") : undefined}
          className="[&>span]:whitespace-normal [&>span]:leading-tight"
        >
          <Stamp meeting={meeting} />
        </span>
        {warns.length > 0 && (
          <span
            role="img"
            aria-label={`${warns.length === 1 ? "Warning" : `${warns.length} warnings`}: ${warns.map((f) => f.message).join(" ")}`}
            title={warnText}
            className="inline-flex items-center gap-0.5 text-amber"
          >
            <TriangleAlert className="size-3.5" strokeWidth={2.25} aria-hidden="true" />
            {warns.length > 1 && <span className="tabular font-heading text-[11px] font-bold">{warns.length}</span>}
          </span>
        )}
      </span>
    </td>
  );
}

function Row({
  meeting,
  selection,
  selected,
  hotelTz,
  viewerTz,
  onSelect,
}: {
  meeting: Meeting;
  selection: Selection;
  selected: boolean;
  hotelTz: string | null;
  viewerTz: string;
  onSelect: (id: number, via: SelectVia) => void;
}) {
  const cancelled = meeting.review_state === "cancelled";
  const others = sharedWith(meeting, selection);
  const executives = [meeting.company_attendees.join(", "), formatLabel(meeting.format)].filter(Boolean).join(" · ");

  function onKeyDown(event: KeyboardEvent<HTMLTableRowElement>) {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(meeting.id, "keyboard");
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const rows = Array.from(
        event.currentTarget.closest("[data-timetable]")?.querySelectorAll<HTMLElement>("[data-tt-row]") ?? [],
      );
      const next = rows[rows.indexOf(event.currentTarget) + (event.key === "ArrowDown" ? 1 : -1)];
      if (next) {
        event.preventDefault();
        next.focus();
      }
    }
  }

  return (
    <tr
      data-tt-row
      tabIndex={0}
      aria-current={selected ? "true" : undefined}
      onClick={() => onSelect(meeting.id, "pointer")}
      onKeyDown={onKeyDown}
      className={[
        "tt-row cursor-pointer text-sm transition-colors duration-150 ease-out [&:last-child>td]:border-b-0",
        "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-navy",
        selected ? "bg-select" : "hover:bg-cream",
        cancelled ? "text-muted" : "text-ink",
      ].join(" ")}
    >
      <TimeCell meeting={meeting} hotelTz={hotelTz} viewerTz={viewerTz} />
      <td className={`tt-company ${cell}`}>
        <span className={`font-bold ${cancelled ? "line-through decoration-[1.5px]" : ""}`}>
          {meeting.company || "Company missing"}
        </span>
        {meeting.ticker && <span className="ml-1.5 font-heading text-[11px] font-bold text-blue">{meeting.ticker}</span>}
        <span className="block text-[13px] leading-snug text-muted">{executives}</span>
      </td>
      <td className={`tt-room ${cell}`} data-empty={meeting.room ? undefined : ""}>
        {meeting.room || "—"}
      </td>
      <td className={`tt-shared ${cell} text-[13px] text-muted`} data-empty={others.length || meeting.removed.length ? undefined : ""}>
        <span className="tt-label tt-dot" aria-hidden="true">
          ·{" "}
        </span>
        <span className="tt-label">with </span>
        {others.join(", ") || "—"}
        {meeting.removed.length > 0 && (
          <span className="block font-semibold text-amber">
            Removing from {meeting.removed.map((a) => a.name).join(", ")}
          </span>
        )}
      </td>
      <StatusCell meeting={meeting} />
    </tr>
  );
}

/**
 * The day-grouped itinerary: one white table per day, columns in a fixed order and fixed widths so
 * they line up from day to day; rows rank by start time.
 */
export function Timetable({
  groups,
  selection,
  selectedId,
  hotelTz,
  viewerTz,
  onSelect,
}: {
  groups: DayGroup[];
  selection: Selection;
  selectedId: number | null;
  hotelTz: string | null;
  viewerTz: string;
  onSelect: (id: number, via: SelectVia) => void;
}) {
  const peopleHeading = selection.kind === "colleague" ? "Shared with" : "Colleagues";
  const root = useRef<HTMLDivElement>(null);

  // Whenever the selection moves (including the default pick on load), keep its row in view.
  useEffect(() => {
    root.current?.querySelector('[data-tt-row][aria-current="true"]')?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <div ref={root} data-timetable>
      {groups.map((group, index) => {
        const headingId = `day-${group.date ?? "missing"}`;
        return (
          <section key={group.date ?? "missing"} aria-labelledby={headingId} className={index === 0 ? "" : "mt-6"}>
            <h2
              id={headingId}
              className={`mb-2 font-heading text-[13px] font-bold uppercase tracking-[0.08em] ${group.date ? "text-blue" : "text-red"}`}
            >
              {dayHeading(group.date)}
            </h2>
            <div className="overflow-hidden rounded-lg border border-line bg-white">
              <table className="tt-table w-full table-fixed border-collapse">
                <colgroup>
                  {/* Whole-pixel widths: fractional cell edges show as hairline seams in the selected-row tint. */}
                  <col className="w-[6.5rem]" />
                  <col />
                  <col className="w-[6.5rem]" />
                  <col className="w-[8.5rem]" />
                  <col className="w-32" />
                </colgroup>
                <thead>
                  <tr className="bg-head text-left font-heading text-[11px] font-bold uppercase tracking-[0.08em] text-muted">
                    <th scope="col" className="border-b border-line px-3 py-2.5">Time</th>
                    <th scope="col" className="border-b border-line px-3 py-2.5">Company</th>
                    <th scope="col" className="border-b border-line px-3 py-2.5">Room</th>
                    <th scope="col" className="border-b border-line px-3 py-2.5">{peopleHeading}</th>
                    <th scope="col" className="border-b border-line px-3 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {group.meetings.map((m) => (
                    <Row
                      key={m.id}
                      meeting={m}
                      selection={selection}
                      selected={m.id === selectedId}
                      hotelTz={hotelTz}
                      viewerTz={viewerTz}
                      onSelect={onSelect}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}
