import { ChevronDown, FileDiff } from "lucide-react";
import type { Revision } from "../../api";
import { Button, ConfirmButton } from "../Button";

export type RevisionBusy = "accept" | "discard" | "separate" | null;

/** The cream strip under the bar while a broker's revised PDF waits for CR's approval. */
export function RevisionStrip({
  revision,
  reviewing,
  busy,
  onToggleReview,
  onAcceptAll,
  onDiscard,
  onKeepSeparate,
}: {
  revision: Revision;
  reviewing: boolean;
  busy: RevisionBusy;
  onToggleReview: () => void;
  onAcceptAll: () => void;
  onDiscard: () => void;
  onKeepSeparate: () => void;
}) {
  const k = revision.changes.length;
  return (
    <section
      aria-label={`Revision ${revision.number}`}
      className="reveal flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-cream-2 px-7 py-2.5"
    >
      <p className="flex min-w-0 items-center gap-2.5 text-sm text-ink">
        <FileDiff className="size-4 shrink-0 text-blue" aria-hidden="true" />
        <span className="min-w-0">
          <span className="font-heading font-bold text-navy">Revision {revision.number}</span> from{" "}
          <span className="font-semibold [overflow-wrap:anywhere]">{revision.pdf_filename}</span> —{" "}
          <span className="tabular font-heading font-bold text-navy">
            {k === 0 ? "no changes found" : `${k} ${k === 1 ? "change" : "changes"}`}
          </span>
        </span>
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {k > 0 && (
          <Button
            size="sm"
            aria-expanded={reviewing}
            onClick={onToggleReview}
            icon={<ChevronDown className={`size-3.5 ${reviewing ? "rotate-180" : ""}`} aria-hidden="true" />}
          >
            {reviewing ? "Back to the timetable" : "Review changes"}
          </Button>
        )}
        <Button
          variant="beige"
          size="sm"
          className="border border-beige-3 focus-visible:outline-navy!"
          loading={busy === "accept"}
          disabled={busy !== null && busy !== "accept"}
          onClick={onAcceptAll}
          title={k === 0 ? "Use the revised PDF as the source from now on" : "Apply every change; calendars update straight away"}
        >
          {k === 0 ? "Use revised PDF" : "Accept all"}
        </Button>
        <ConfirmButton
          size="sm"
          label="Discard"
          confirmLabel="Discard for good?"
          subject={`revision ${revision.number}`}
          loading={busy === "discard"}
          disabled={busy !== null && busy !== "discard"}
          onConfirm={onDiscard}
          title="Ignore this PDF; nothing changes"
        />
      </div>
      <button
        type="button"
        onClick={onKeepSeparate}
        disabled={busy !== null}
        className="ml-auto rounded-sm text-[13px] font-semibold text-blue underline decoration-blue/40 underline-offset-[3px] transition-colors duration-150 hover:decoration-blue disabled:cursor-progress disabled:opacity-60"
      >
        {busy === "separate" ? "Making a new conference…" : "Not the same conference? Keep it separate"}
      </button>
    </section>
  );
}
