import {
  Calendar,
  CalendarCheck,
  CalendarX,
  Check,
  ChevronDown,
  CircleAlert,
  ExternalLink,
  Loader2,
  RefreshCw,
  TriangleAlert,
  Users,
  X,
} from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import {
  ApiError,
  confirmMeeting,
  deleteMeeting,
  errorMessage,
  patchMeeting,
  pdfUrl,
  revisionPdfUrl,
  unconfirmMeeting,
  type Analyst,
  type Attendee,
  type ConferenceDetail,
  type Meeting,
  type MeetingFormat,
  type MeetingUpdate,
  type Revision,
  type RevisionChange,
} from "../../api";
import { formatLabel } from "../../lib/format";
import { readableSummary } from "../../lib/revision";
import { isOnCalendars, sharedWith, type Selection } from "../../lib/review";
import { Button, ConfirmButton } from "../Button";
import { fieldLabelClass, inputClass } from "../fields";
import { Note } from "../Note";
import { AttendeePicker } from "./AttendeePicker";

export type Run = (promise: Promise<ConferenceDetail>) => Promise<ConferenceDetail>;

const FORMATS: MeetingFormat[] = ["one_on_one", "group", "meal", "other"];

// ---------- fields ----------

type FieldKind = "text" | "time" | "date" | "textarea";

/**
 * A field that saves on blur (and Enter in single-line fields) when its value changed. While it has
 * focus it keeps CR's draft even if fresh detail arrives from another save; Esc puts the saved value back.
 */
function Field({
  label,
  value,
  kind = "text",
  placeholder,
  disabled,
  hint,
  className = "",
  validate,
  onSave,
}: {
  label: string;
  value: string;
  kind?: FieldKind;
  placeholder?: string;
  disabled?: boolean;
  hint?: ReactNode;
  className?: string;
  validate?: (value: string) => string | null;
  onSave: (value: string) => Promise<unknown>;
}) {
  const id = useId();
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focused = useRef(false);
  const inFlight = useRef<string | null>(null);

  useEffect(() => {
    if (!focused.current) setDraft(value);
  }, [value]);

  async function commit(target: HTMLInputElement | HTMLTextAreaElement) {
    if (target instanceof HTMLInputElement && target.validity.badInput) {
      setError(kind === "time" ? "Enter a full time, hours and minutes." : "Enter a full date.");
      return;
    }
    const next = draft.trim();
    if (next === value.trim() || next === inFlight.current) return;
    const problem = validate?.(next) ?? null;
    if (problem) {
      setError(problem);
      return;
    }
    inFlight.current = next;
    setSaving(true);
    setError(null);
    try {
      await onSave(next);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      inFlight.current = null;
      setSaving(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) {
    if (event.key === "Escape" && draft !== value) {
      event.stopPropagation(); // revert first; a second Esc may close the drawer
      setDraft(value);
      setError(null);
    } else if (event.key === "Enter" && kind !== "textarea") {
      event.preventDefault();
      commit(event.currentTarget);
    }
  }

  const props = {
    id,
    value: draft,
    disabled,
    placeholder,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": error ? `${id}-error` : undefined,
    onFocus: () => {
      focused.current = true;
    },
    onChange: (event: { target: { value: string } }) => {
      setDraft(event.target.value);
      setError(null);
    },
    onBlur: (event: { currentTarget: HTMLInputElement | HTMLTextAreaElement }) => {
      focused.current = false;
      commit(event.currentTarget);
    },
    onKeyDown,
  };

  return (
    <div className={className}>
      <label htmlFor={id} className={`${fieldLabelClass} flex items-center gap-1.5`}>
        {label}
        {hint}
        {saving && <Loader2 className="size-3 animate-spin" aria-label="Saving" />}
      </label>
      {kind === "textarea" ? (
        <textarea {...props} rows={2} className={`${inputClass} block resize-y py-2 font-semibold leading-snug`} />
      ) : (
        <input {...props} type={kind} className={`${inputClass} tabular h-9 font-semibold`} />
      )}
      {error && (
        <p id={`${id}-error`} role="alert" className="mt-1 text-xs font-semibold text-red">
          {error}
        </p>
      )}
    </div>
  );
}

function FormatField({ value, disabled, onSave }: { value: MeetingFormat; disabled?: boolean; onSave: (v: MeetingFormat) => Promise<unknown> }) {
  const id = useId();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div>
      <label htmlFor={id} className={`${fieldLabelClass} flex items-center gap-1.5`}>
        Format
        {saving && <Loader2 className="size-3 animate-spin" aria-label="Saving" />}
      </label>
      <span className="relative block">
        <select
          id={id}
          value={value}
          disabled={disabled || saving}
          onChange={async (event) => {
            setSaving(true);
            setError(null);
            try {
              await onSave(event.target.value as MeetingFormat);
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setSaving(false);
            }
          }}
          className={`${inputClass} h-9 appearance-none pr-8 font-semibold`}
        >
          {FORMATS.map((f) => (
            <option key={f} value={f}>
              {formatLabel(f)}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden="true" />
      </span>
      {error && (
        <p role="alert" className="mt-1 text-xs font-semibold text-red">
          {error}
        </p>
      )}
    </div>
  );
}

// ---------- notes and sync lines ----------

function MeetingNotes({ meeting, selection, run }: { meeting: Meeting; selection: Selection; run: Run }) {
  const [dismissing, setDismissing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const blocks = meeting.flags.filter((f) => f.severity === "block");
  const warns = meeting.flags.filter((f) => f.severity === "warn" && f.code !== "unmatched_name");
  const others = selection.kind === "colleague" ? sharedWith(meeting, selection).length : meeting.attendees.length;
  const shared = meeting.attendees.length > 1 && meeting.review_state !== "cancelled";

  async function dismiss(name: string) {
    setDismissing(name);
    setError(null);
    try {
      await run(patchMeeting(meeting.id, { ignored_names: [...meeting.ignored_names, name] }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDismissing(null);
    }
  }

  if (!blocks.length && !warns.length && !meeting.unmatched_names.length && !shared) return null;
  return (
    <div className="mb-4 space-y-2">
      {blocks.length > 0 && (
        <Note tone="red" icon={<CircleAlert aria-hidden="true" />}>
          <ul className="space-y-0.5">
            {blocks.map((f) => (
              <li key={f.code}>{f.message}</li>
            ))}
          </ul>
        </Note>
      )}
      {(warns.length > 0 || meeting.unmatched_names.length > 0) && (
        <Note tone="amber" icon={<TriangleAlert aria-hidden="true" />}>
          <ul className="space-y-1">
            {warns.map((f, i) => (
              <li key={`${f.code}-${i}`}>{f.message}</li>
            ))}
            {meeting.unmatched_names.map((name) => (
              <li key={name} className="flex items-center justify-between gap-3">
                <span>“{name}” isn't on the roster.</span>
                <Button
                  size="sm"
                  className="h-7 border-amber-line"
                  loading={dismissing === name}
                  onClick={() => dismiss(name)}
                  title={`Stop flagging “${name}” on this meeting`}
                >
                  Dismiss
                </Button>
              </li>
            ))}
          </ul>
          {error && <p className="mt-1 text-red">{error}</p>}
        </Note>
      )}
      {shared && (
        <Note tone="amber" icon={<Users aria-hidden="true" />}>
          Shared with {others} {others === 1 ? "colleague" : "colleagues"} —{" "}
          {meeting.status === "confirmed" ? "edits update every calendar." : "verifying updates every calendar."}
        </Note>
      )}
    </div>
  );
}

function syncLine(a: Attendee, meeting: Meeting): { icon: ReactNode; text: string; tone: string } {
  const owner = `${a.name}'s calendar`;
  switch (a.sync) {
    case "sent":
      return {
        icon: <CalendarCheck aria-hidden="true" />,
        text: meeting.status === "draft" ? `On ${owner} · edits wait until you verify again` : `On ${owner}`,
        tone: "text-green",
      };
    case "changed":
      return { icon: <RefreshCw aria-hidden="true" />, text: `${a.name} · Changed — updating`, tone: "text-amber" };
    case "failed":
      return { icon: <CircleAlert aria-hidden="true" />, text: `${a.name} · Failed: ${a.sync_error ?? "unknown error"}`, tone: "text-red" };
    case "cancelled":
      return { icon: <CalendarX aria-hidden="true" />, text: `Removed from ${owner}`, tone: "text-muted" };
    case "not_sent":
      return {
        icon: <Calendar aria-hidden="true" />,
        text: meeting.status === "confirmed" ? `${a.name} · Not on the calendar yet` : `Goes to ${owner} when verified`,
        tone: "text-muted",
      };
  }
}

function SyncLines({ meeting }: { meeting: Meeting }) {
  if (!meeting.attendees.length && !meeting.removed.length) return null;
  return (
    <ul aria-label="Calendar status" className="mb-4 space-y-1 text-[13px] font-semibold">
      {meeting.attendees.map((a) => {
        const line = syncLine(a, meeting);
        return (
          <li key={a.analyst_id} className={`flex items-start gap-2 ${line.tone} [&>svg]:mt-0.5 [&>svg]:size-3.5 [&>svg]:shrink-0`}>
            {line.icon}
            <span className="[overflow-wrap:anywhere]">{line.text}</span>
          </li>
        );
      })}
      {meeting.removed.map((a) => (
        <li
          key={`removed-${a.analyst_id}`}
          className={`flex items-start gap-2 ${a.sync === "failed" ? "text-red" : "text-amber"} [&>svg]:mt-0.5 [&>svg]:size-3.5 [&>svg]:shrink-0`}
        >
          <CalendarX aria-hidden="true" />
          <span className="[overflow-wrap:anywhere]">
            {a.sync === "failed"
              ? `Couldn't remove from ${a.name}'s calendar: ${a.sync_error ?? "unknown error"}`
              : `Removing from ${a.name}'s calendar`}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ---------- the editor for one meeting ----------

function MeetingEditor({
  meeting,
  selection,
  roster,
  run,
}: {
  meeting: Meeting;
  selection: Selection;
  roster: Analyst[] | null;
  run: Run;
}) {
  const cancelled = meeting.review_state === "cancelled";
  const save = (body: MeetingUpdate) => run(patchMeeting(meeting.id, body));
  const lines = (text: string) =>
    text
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);

  return (
    <>
      <MeetingNotes meeting={meeting} selection={selection} run={run} />
      {cancelled && (
        <Note tone="info" icon={<CalendarX aria-hidden="true" />} className="mb-4">
          Cancelled. It stays here struck through so nothing disappears.
        </Note>
      )}
      <SyncLines meeting={meeting} />
      <div className="grid grid-cols-2 gap-x-3 gap-y-3">
        <Field label="Date" kind="date" value={meeting.date ?? ""} disabled={cancelled} onSave={(v) => save({ date: v || null })} />
        <FormatField value={meeting.format} disabled={cancelled} onSave={(format) => save({ format })} />
        <Field label="Start" kind="time" value={meeting.start ?? ""} disabled={cancelled} onSave={(v) => save({ start: v || null })} />
        <Field
          label="End"
          kind="time"
          value={meeting.end ?? ""}
          disabled={cancelled}
          hint={meeting.end_assumed ? <span className="normal-case tracking-normal text-amber">(assumed)</span> : null}
          onSave={(v) => save({ end: v || null })}
        />
        <Field label="Room" value={meeting.room} placeholder="Room" disabled={cancelled} onSave={(v) => save({ room: v })} />
        <Field label="Ticker" value={meeting.ticker ?? ""} placeholder="Ticker" disabled={cancelled} onSave={(v) => save({ ticker: v || null })} />
        <Field
          label="Company"
          className="col-span-2"
          value={meeting.company}
          disabled={cancelled}
          validate={(v) => (v ? null : "Enter the company's name.")}
          onSave={(v) => save({ company: v })}
        />
        <Field
          label="Executives"
          kind="textarea"
          className="col-span-2"
          value={meeting.company_attendees.join("\n")}
          placeholder="One per line, e.g. Dana Shore, CFO"
          disabled={cancelled}
          onSave={(v) => save({ company_attendees: lines(v) })}
        />
        <div className="col-span-2">
          <AttendeePicker
            attendees={meeting.attendees}
            roster={roster}
            disabled={cancelled}
            onChange={async (ids) => {
              await save({ attendee_ids: ids });
            }}
          />
        </div>
        <Field
          label="Notes"
          kind="textarea"
          className="col-span-2"
          value={meeting.notes}
          placeholder="Anything colleagues should see in the calendar entry"
          disabled={cancelled}
          onSave={(v) => save({ notes: v })}
        />
      </div>
    </>
  );
}

function MeetingActions({ meeting, run }: { meeting: Meeting; run: Run }) {
  const [busy, setBusy] = useState<"verify" | "unverify" | "delete" | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const onCalendars = isOnCalendars(meeting);

  async function act(kind: "verify" | "unverify" | "delete", promise: () => Promise<ConferenceDetail>) {
    setBusy(kind);
    setError(null);
    try {
      await run(promise());
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, errorMessage(err)));
    } finally {
      setBusy(null);
    }
  }

  if (meeting.review_state === "cancelled") return null;
  return (
    <>
      {error && (
        <div role="alert" className="mb-3 rounded-md border border-red-line bg-red-bg px-3 py-2.5 text-[13px] font-semibold text-red">
          <p>{error.detail}</p>
          {error.flags.length > 0 && (
            <ul className="mt-1 list-disc space-y-0.5 pl-4 font-medium">
              {error.flags.map((f) => (
                <li key={f.code}>{f.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="flex gap-2.5">
        {meeting.status === "draft" ? (
          <Button
            variant="primary"
            className="flex-1"
            loading={busy === "verify"}
            disabled={busy !== null}
            icon={<Check className="size-4" strokeWidth={2.5} aria-hidden="true" />}
            onClick={() => act("verify", () => confirmMeeting(meeting.id))}
          >
            Verify meeting
          </Button>
        ) : (
          <Button
            className="flex-1"
            loading={busy === "unverify"}
            disabled={busy !== null}
            title="Back to draft. Calendar entries stay as they are until you verify it again."
            onClick={() => act("unverify", () => unconfirmMeeting(meeting.id))}
          >
            Unverify
          </Button>
        )}
        <ConfirmButton
          loading={busy === "delete"}
          disabled={busy !== null && busy !== "delete"}
          label={onCalendars ? "Cancel meeting" : "Delete"}
          confirmLabel={onCalendars ? "Cancel for good?" : "Delete for good?"}
          subject={meeting.company}
          title={
            onCalendars
              ? "Takes it off every colleague's calendar; it stays here struck through."
              : "Removes it from this conference. It isn't on any calendar."
          }
          onConfirm={() => act("delete", () => deleteMeeting(meeting.id))}
        />
      </div>
    </>
  );
}

// ---------- the panel ----------

export interface RevisionSource {
  revision: Revision;
  change: RevisionChange | null;
}

/**
 * The source panel: the PDF page, the selected meeting's editable fields, its flags and the Verify
 * action. While a revision is being reviewed it shows the revised PDF at the selected change instead.
 * Docked at >=1281px; a right drawer below that.
 */
export function SourcePanel({
  detail,
  meeting,
  selection,
  roster,
  run,
  revisionSource,
  drawer,
  open,
  onClose,
  headingRef,
}: {
  detail: ConferenceDetail;
  meeting: Meeting | null;
  selection: Selection;
  roster: Analyst[] | null;
  run: Run;
  revisionSource: RevisionSource | null;
  drawer: boolean;
  open: boolean;
  onClose: () => void;
  headingRef: RefObject<HTMLHeadingElement | null>;
}) {
  const page = revisionSource ? (revisionSource.change?.new?.page ?? null) : (meeting?.source_page ?? null);
  const filename = revisionSource ? revisionSource.revision.pdf_filename : detail.pdf_filename;
  const src = revisionSource ? revisionPdfUrl(revisionSource.revision.id, page) : pdfUrl(detail.id, page);
  const hidden = drawer && !open;

  return (
    <aside
      aria-labelledby="source-heading"
      inert={hidden || undefined}
      className={[
        "flex flex-col overflow-y-auto overscroll-contain border-line bg-white",
        drawer
          ? // Visibility flips at once on opening (so focus can land) and only after the slide on closing.
            `absolute inset-y-0 right-0 z-20 w-[min(420px,100%)] border-l shadow-[0_8px_24px_rgba(24,41,88,0.18)] duration-200 ease-out ${hidden ? "invisible translate-x-[calc(100%+32px)] transition-[translate,visibility]" : "visible translate-x-0 transition-[translate]"}`
          : "border-l",
      ].join(" ")}
    >
      <div className="flex-1 px-[22px] pb-5 pt-5">
        <div className="flex items-start justify-between gap-3">
          <h2
            id="source-heading"
            ref={headingRef}
            tabIndex={-1}
            title={filename}
            className="min-w-0 truncate rounded-sm pt-0.5 font-heading text-xs font-bold uppercase tracking-[0.1em] text-muted"
          >
            Source · {filename}
            {page ? ` · page ${page}` : ""}
          </h2>
          {drawer && (
            <Button size="sm" onClick={onClose} icon={<X className="size-3.5" aria-hidden="true" />} className="-mt-1">
              Close
            </Button>
          )}
        </div>
        <div className="mt-2.5 rounded-md border border-line bg-cream-2 p-2">
          <iframe key={src} title="Source PDF page" src={src} className="block h-[330px] w-full rounded-[3px] bg-white" />
        </div>
        <p className="mb-4 mt-1.5 text-right">
          <a
            href={src}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-sm text-xs font-semibold text-blue underline decoration-blue/40 hover:decoration-blue"
          >
            Open the PDF in a new tab
            <ExternalLink className="size-3" aria-hidden="true" />
          </a>
        </p>

        {revisionSource ? (
          <Note tone="info">
            {revisionSource.change ? (
              <>
                <p className="font-bold">{revisionSource.change.company}</p>
                <p className="mt-0.5 font-medium">{readableSummary(revisionSource.change)}</p>
              </>
            ) : (
              <p className="font-medium">The broker's revised PDF. Pick a change to see its page.</p>
            )}
            <p className="mt-1.5 font-medium text-muted">Nothing changes on calendars until you apply.</p>
          </Note>
        ) : meeting ? (
          <MeetingEditor key={meeting.id} meeting={meeting} selection={selection} roster={roster} run={run} />
        ) : (
          <p className="text-sm font-medium text-muted">
            {detail.meetings.length === 0
              ? "Nothing was extracted. Check the PDF here and add any meetings it lists."
              : "Pick a meeting to check it against the PDF."}
          </p>
        )}
      </div>
      {meeting && !revisionSource && meeting.review_state !== "cancelled" && (
        <div className="sticky bottom-0 border-t border-line bg-white px-[22px] pb-5 pt-4">
          <MeetingActions key={meeting.id} meeting={meeting} run={run} />
        </div>
      )}
    </aside>
  );
}
