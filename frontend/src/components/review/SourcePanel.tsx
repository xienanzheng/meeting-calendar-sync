import {
  Calendar,
  CalendarCheck,
  CalendarX,
  Check,
  ChevronDown,
  CircleAlert,
  Loader2,
  RefreshCw,
  TriangleAlert,
  Users,
  X,
} from "lucide-react";
import {
  lazy,
  Suspense,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
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
import { dayHeading, formatLabel, formatTime12 } from "../../lib/format";
import { readableSummary } from "../../lib/revision";
import { conferenceDates, isOnCalendars, sharedWith, type Selection } from "../../lib/review";
import { Button, ConfirmButton } from "../Button";
import { fieldLabelClass, inputClass } from "../fields";
import { Note } from "../Note";
import { AttendeePicker } from "./AttendeePicker";
import type { RowTarget } from "./PdfViewer";

// pdf.js is large; it loads with the first source panel, not with the app.
const PdfViewer = lazy(() => import("./PdfViewer"));

export type Run = (promise: Promise<ConferenceDetail>) => Promise<ConferenceDetail>;

const FORMATS: MeetingFormat[] = ["one_on_one", "group", "meal", "other"];

// ---------- fields ----------

type FieldKind = "text" | "textarea";

/**
 * A field that saves on blur (and Enter in single-line fields) when its value changed. While it has
 * focus it keeps CR's draft even if fresh detail arrives from another save; Esc puts the saved value back.
 * After its own save it shows the saved value as the server wrote it (e.g. "2pm" comes back "2:00 PM").
 */
function Field({
  label,
  value,
  kind = "text",
  placeholder,
  disabled,
  hint,
  className = "",
  inputClassName = "",
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
  inputClassName?: string;
  validate?: (value: string) => string | null;
  onSave: (value: string) => Promise<unknown>;
}) {
  const id = useId();
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saves, setSaves] = useState(0);
  const synced = useRef(0);
  const focused = useRef(false);
  const inFlight = useRef<string | null>(null);

  useEffect(() => {
    if (!focused.current || synced.current !== saves) {
      synced.current = saves;
      setDraft(value);
    }
  }, [value, saves]);

  async function commit() {
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
      setSaves((n) => n + 1);
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
      commit();
    }
  }

  const props = {
    id,
    value: draft,
    disabled,
    placeholder,
    autoComplete: "off",
    "aria-invalid": error ? true : undefined,
    "aria-describedby": error ? `${id}-error` : undefined,
    onFocus: () => {
      focused.current = true;
    },
    onChange: (event: { target: { value: string } }) => {
      setDraft(event.target.value);
      setError(null);
    },
    onBlur: () => {
      focused.current = false;
      commit();
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
        <input {...props} type="text" className={`${inputClass} tabular h-9 font-semibold ${inputClassName}`} />
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

const OTHER_DATE = "other";

/**
 * The meeting's date as one of the conference's days, written like the day headings ("Wednesday,
 * December 2") so no browser locale can turn Dec 2 into 02/12. "Other date…" opens a date input for a
 * day outside the conference, with the date it reads spelled out under it.
 */
function DateField({
  value,
  dates,
  disabled,
  className = "",
  onSave,
}: {
  value: string | null;
  dates: string[];
  disabled?: boolean;
  className?: string;
  onSave: (date: string) => Promise<unknown>;
}) {
  const id = useId();
  const otherRef = useRef<HTMLInputElement>(null);
  const [other, setOther] = useState(false);
  const [otherDraft, setOtherDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const options = value && !dates.includes(value) ? [...dates, value].sort() : dates;

  async function save(next: string) {
    if (!next || next === value) {
      setOther(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(next);
      setOther(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={className}>
      <label htmlFor={id} className={`${fieldLabelClass} flex items-center gap-1.5`}>
        Date
        {saving && <Loader2 className="size-3 animate-spin" aria-label="Saving" />}
      </label>
      <span className="relative block">
        <select
          id={id}
          value={other ? OTHER_DATE : (value ?? "")}
          disabled={disabled || saving}
          aria-invalid={error ? true : undefined}
          onChange={(event) => {
            const next = event.target.value;
            setError(null);
            if (next === OTHER_DATE) {
              setOther(true);
              setOtherDraft(value ?? "");
              requestAnimationFrame(() => otherRef.current?.focus());
            } else {
              setOther(false);
              save(next);
            }
          }}
          className={`${inputClass} h-9 appearance-none pr-8 font-semibold`}
        >
          {!value && (
            <option value="" disabled>
              Pick a date
            </option>
          )}
          {options.map((d) => (
            <option key={d} value={d}>
              {dayHeading(d)}
            </option>
          ))}
          <option value={OTHER_DATE}>Other date…</option>
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden="true" />
      </span>
      {other && (
        <div className="mt-2">
          <div className="flex gap-2">
            <label htmlFor={`${id}-other`} className="sr-only">
              Other date
            </label>
            <input
              ref={otherRef}
              id={`${id}-other`}
              type="date"
              value={otherDraft}
              disabled={saving}
              onChange={(event) => setOtherDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  save(otherDraft);
                } else if (event.key === "Escape") {
                  event.stopPropagation(); // close the picker, not the drawer
                  setOther(false);
                }
              }}
              className={`${inputClass} tabular h-9 font-semibold`}
            />
            <Button size="sm" className="h-9" disabled={!otherDraft} loading={saving} onClick={() => save(otherDraft)}>
              Use date
            </Button>
          </div>
          {otherDraft && (
            <p className="mt-1 text-xs font-medium text-muted">
              {dayHeading(otherDraft)}, {otherDraft.slice(0, 4)}
            </p>
          )}
        </div>
      )}
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
  dates,
  selection,
  roster,
  run,
}: {
  meeting: Meeting;
  dates: string[];
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
        <DateField
          className="col-span-2"
          value={meeting.date}
          dates={dates}
          disabled={cancelled}
          onSave={(date) => save({ date })}
        />
        {/* Times read and save as the table prints them ("2:30 PM"); the server also takes "14:30" or "2pm". */}
        <Field
          label="Start"
          value={meeting.start ? formatTime12(meeting.start) : ""}
          placeholder="e.g. 2:30 PM"
          disabled={cancelled}
          onSave={(v) => save({ start: v || null })}
        />
        <Field
          label="End"
          value={meeting.end ? formatTime12(meeting.end) : ""}
          placeholder="e.g. 3:15 PM"
          disabled={cancelled}
          hint={meeting.end_assumed ? <span className="normal-case tracking-normal text-amber">(assumed)</span> : null}
          onSave={(v) => save({ end: v || null })}
        />
        <Field label="Room" value={meeting.room} placeholder="Room" disabled={cancelled} onSave={(v) => save({ room: v })} />
        <FormatField value={meeting.format} disabled={cancelled} onSave={(format) => save({ format })} />
        <div className="col-span-2 grid grid-cols-[minmax(0,1fr)_6.5rem] gap-x-3">
          <Field
            label="Company"
            value={meeting.company}
            disabled={cancelled}
            validate={(v) => (v ? null : "Enter the company's name.")}
            onSave={(v) => save({ company: v })}
          />
          <Field
            label="Ticker"
            value={meeting.ticker ?? ""}
            placeholder="Ticker"
            disabled={cancelled}
            inputClassName="uppercase placeholder:normal-case"
            onSave={(v) => save({ ticker: v ? v.toUpperCase() : null })}
          />
        </div>
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
  // The file (versioned by revision, so an applied revision reloads it) and the same file at its page.
  const [fileUrl, openUrl] = revisionSource
    ? [revisionPdfUrl(revisionSource.revision.id), revisionPdfUrl(revisionSource.revision.id, page)]
    : [pdfUrl(detail.id, null, detail.revision_number), pdfUrl(detail.id, page, detail.revision_number)];
  // The row to highlight: the meeting's, or the revised row of the selected change (a removed one has none).
  const proposed = revisionSource?.change?.new ?? null;
  const target: RowTarget | null = revisionSource
    ? proposed && { company: proposed.company, ticker: proposed.ticker }
    : meeting && { company: meeting.company, ticker: meeting.ticker };
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
        <div className="mb-4 mt-2.5">
          <Suspense
            fallback={
              <div role="status" aria-label="Loading the PDF" className="h-[368px] rounded-md border border-line bg-cream-2 p-2 pt-[45px]">
                <div className="h-full rounded-[3px] bg-white" />
              </div>
            }
          >
            <PdfViewer url={fileUrl} openUrl={openUrl} page={page} target={target} />
          </Suspense>
        </div>

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
          <MeetingEditor
            key={meeting.id}
            meeting={meeting}
            dates={conferenceDates(detail)}
            selection={selection}
            roster={roster}
            run={run}
          />
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
