import { ArrowRight, Check, FileText } from "lucide-react";
import type { Meeting, Revision, RevisionChange, RevisionChangeKind } from "../../api";
import { dayHeading, formatTime12 } from "../../lib/format";
import { fieldLabel, formatValue, readableSummary } from "../../lib/revision";
import { isOnCalendars } from "../../lib/review";
import { Button } from "../Button";

const KINDS: Record<RevisionChangeKind, { label: string; className: string }> = {
  changed: { label: "Changed", className: "border-blue/40 bg-select text-navy" },
  added: { label: "New", className: "border-green bg-white text-green" },
  removed: { label: "Dropped", className: "border-red-line bg-red-bg text-red" },
};

const andList = (names: string[]) =>
  names.length <= 1 ? (names[0] ?? "") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;

function ChangeDetails({ change, meeting }: { change: RevisionChange; meeting: Meeting | undefined }) {
  if (change.kind === "changed") {
    return (
      <table className="mt-2 text-[13px]">
        <thead className="sr-only">
          <tr>
            <th scope="col">Field</th>
            <th scope="col">Before</th>
            <th scope="col">After</th>
          </tr>
        </thead>
        <tbody>
          {change.fields.map((f) => (
            <tr key={f.field} className="align-top">
              <th scope="row" className="w-24 py-0.5 pr-3 text-left font-semibold text-muted">
                {fieldLabel(f.field)}
              </th>
              <td className="py-0.5 pr-3 text-muted">{formatValue(f.field, f.before)}</td>
              <td className="py-0.5 pr-3 text-muted">
                <ArrowRight className="mt-0.5 size-3.5" aria-label="becomes" />
              </td>
              <td className="py-0.5 font-semibold text-ink">{formatValue(f.field, f.after)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  if (change.kind === "added" && change.new) {
    const m = change.new;
    const time = m.start ? `${formatTime12(m.start)}–${formatTime12(m.end)}` : "Time missing";
    return (
      <p className="tabular mt-1.5 text-[13px] text-ink">
        <span className="font-semibold">{m.date ? dayHeading(m.date) : "Date missing"}</span> · {time} · {m.room || "No room"}
        {" · "}
        {m.firm_attendees.length ? m.firm_attendees.join(", ") : <span className="font-semibold text-red">No colleague</span>}
      </p>
    );
  }
  if (change.kind === "removed") {
    const names = meeting?.attendees.map((a) => a.name) ?? [];
    return meeting && isOnCalendars(meeting) && names.length ? (
      <p className="mt-1.5 text-[13px] font-semibold text-amber">Will be removed from {andList(names)}'s calendars</p>
    ) : (
      <p className="mt-1.5 text-[13px] text-muted">It was never on a calendar, so it's simply deleted.</p>
    );
  }
  return null;
}

/**
 * The revision review, in place of the timetable: every broker change with a tick (all on to start),
 * what it does, and one Apply for the ticked ones. Picking a change shows its page of the revised PDF.
 */
export function RevisionReview({
  revision,
  meetings,
  accepted,
  selectedChangeId,
  applying,
  onToggle,
  onSetAll,
  onSelectChange,
  onApply,
  onClose,
}: {
  revision: Revision;
  meetings: Meeting[];
  accepted: ReadonlySet<string>;
  selectedChangeId: string | null;
  applying: boolean;
  onToggle: (id: string) => void;
  onSetAll: (on: boolean) => void;
  onSelectChange: (id: string) => void;
  onApply: () => void;
  onClose: () => void;
}) {
  const k = accepted.size;
  const total = revision.changes.length;
  const byId = new Map(meetings.map((m) => [m.id, m]));
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-3.5 gap-y-1">
        <h1 className="text-[28px] font-bold leading-tight text-navy">What changed in revision {revision.number}</h1>
        <p className="text-sm text-muted">
          {revision.pdf_filename} · {total} {total === 1 ? "change" : "changes"}
        </p>
      </div>
      <div className="mt-3.5 flex flex-wrap items-center gap-3 text-[13px]">
        <span className="font-semibold text-ink">
          <span className="tabular font-heading font-bold">{k}</span> of {total} ticked
        </span>
        <button
          type="button"
          onClick={() => onSetAll(k !== total)}
          className="rounded-sm font-semibold text-blue underline decoration-blue/40 underline-offset-[3px] hover:decoration-blue"
        >
          {k === total ? "Untick all" : "Tick all"}
        </button>
      </div>

      <ul className="mt-4 space-y-2.5">
        {revision.changes.map((change) => {
          const on = accepted.has(change.id);
          const selected = change.id === selectedChangeId;
          const kind = KINDS[change.kind];
          const titleId = `change-${change.id}`;
          const page = change.new?.page ?? null;
          return (
            <li
              key={change.id}
              onClick={() => onSelectChange(change.id)}
              className={[
                "flex cursor-pointer items-start gap-3 rounded-lg border px-4 py-3 transition-colors duration-150 ease-out",
                selected ? "border-blue/40 bg-select" : "border-line bg-white hover:bg-cream",
              ].join(" ")}
            >
              <input
                type="checkbox"
                checked={on}
                onChange={() => onToggle(change.id)}
                onClick={(event) => event.stopPropagation()}
                aria-labelledby={titleId}
                className="mt-1 size-4 shrink-0 cursor-pointer accent-navy"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-[4px] border px-1.5 py-0.5 font-heading text-[11px] font-bold uppercase leading-none tracking-[0.08em] ${kind.className}`}
                  >
                    {kind.label}
                  </span>
                  <span id={titleId} className="font-bold text-ink">
                    <span className="sr-only">{kind.label}: </span>
                    {change.company}
                  </span>
                </div>
                <p className="mt-0.5 text-[13px] text-muted">{readableSummary(change)}</p>
                <ChangeDetails change={change} meeting={change.meeting_id ? byId.get(change.meeting_id) : undefined} />
                {!on && (
                  <p className="mt-1.5 text-xs font-semibold text-muted">
                    Unticked: this stays as it is and comes up again with the next revision.
                  </p>
                )}
              </div>
              <Button
                size="sm"
                className="shrink-0"
                aria-pressed={selected}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectChange(change.id);
                }}
                icon={<FileText className="size-3.5" aria-hidden="true" />}
              >
                {page ? `Page ${page}` : "PDF"}
                <span className="sr-only"> of the revised PDF for {change.company}</span>
              </Button>
            </li>
          );
        })}
      </ul>

      <div className="sticky bottom-0 -mx-1 mt-5 flex flex-wrap items-center gap-3 border-t border-line bg-cream px-1 pb-5 pt-4">
        <Button
          variant="primary"
          loading={applying}
          disabled={k === 0}
          onClick={onApply}
          icon={<Check className="size-4" strokeWidth={2.5} aria-hidden="true" />}
        >
          Apply {k} {k === 1 ? "change" : "changes"}
        </Button>
        <Button onClick={onClose} disabled={applying}>
          Back to the timetable
        </Button>
        <span className="text-[13px] text-muted">
          {k === 0
            ? "Tick at least one change, or discard the revision."
            : `${revision.unchanged_count} ${revision.unchanged_count === 1 ? "meeting" : "meetings"} unchanged`}
        </span>
      </div>
    </div>
  );
}
