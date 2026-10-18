import { Check, Plus } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { addMeeting, errorMessage, type Analyst, type ConferenceDetail } from "../../api";
import { Button } from "../Button";
import { fieldLabelClass, inputClass } from "../fields";
import { DateSelect, OTHER_DATE, OtherDateInput } from "./DateSelect";

type TimeField = "start" | "end";

/**
 * "Add meeting" under the timetable: collapsed to one quiet button, it opens an inline form for a
 * meeting the PDF missed. The new meeting starts as a draft like any other. Dates and times read as the
 * source panel's do: a pick from the conference's days, and times typed like the table prints them.
 */
export function AddMeetingRow({
  cid,
  knownIds,
  roster,
  dates,
  defaultDate,
  defaultColleague,
  startOpen = false,
  run,
  onAdded,
}: {
  cid: number;
  /** The meetings on screen before the add, to find the one the server created. */
  knownIds: number[];
  roster: Analyst[] | null;
  /** The conference's days for the date select (`conferenceDates`). */
  dates: string[];
  defaultDate: string | null;
  defaultColleague: number | null;
  startOpen?: boolean;
  run: (promise: Promise<ConferenceDetail>) => Promise<ConferenceDetail>;
  /** Called with the new meeting's id so the page can select it. */
  onAdded: (meetingId: number | null) => void;
}) {
  const id = useId();
  const [open, setOpen] = useState(startOpen);
  const [company, setCompany] = useState("");
  const [date, setDate] = useState(defaultDate ?? "");
  const [otherDate, setOtherDate] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [room, setRoom] = useState("");
  const [ids, setIds] = useState<number[]>(defaultColleague ? [defaultColleague] : []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The server's "Couldn't read the time '2:3x'…" belongs under the field that holds '2:3x'.
  const [timeError, setTimeError] = useState<{ field: TimeField; message: string } | null>(null);
  const companyRef = useRef<HTMLInputElement>(null);
  const otherRef = useRef<HTMLInputElement>(null);
  const timeRefs = { start: useRef<HTMLInputElement>(null), end: useRef<HTMLInputElement>(null) };
  const toggleRef = useRef<HTMLButtonElement>(null);
  const opened = useRef(false);

  useEffect(() => {
    if (open && opened.current) companyRef.current?.focus();
    if (!open && opened.current) toggleRef.current?.focus();
  }, [open]);

  function expand() {
    opened.current = true;
    setDate(defaultDate ?? "");
    setOtherDate(false);
    setIds(defaultColleague ? [defaultColleague] : []);
    setError(null);
    setTimeError(null);
    setOpen(true);
  }

  function reset() {
    setCompany("");
    setStart("");
    setEnd("");
    setRoom("");
    setOtherDate(false);
    setError(null);
    setTimeError(null);
  }

  /** Which time field a server message is about, from the value it quotes. */
  function timeFieldOf(message: string): TimeField | null {
    const quoted = /Couldn't read the time '(.*?)'/.exec(message)?.[1];
    if (quoted === undefined) return null;
    if (quoted === start.trim()) return "start";
    if (quoted === end.trim()) return "end";
    return null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!company.trim()) {
      setError("Enter the company's name.");
      companyRef.current?.focus();
      return;
    }
    setSaving(true);
    setError(null);
    setTimeError(null);
    try {
      const before = new Set(knownIds);
      const detail = await run(
        addMeeting(cid, {
          company: company.trim(),
          date: date || null,
          start: start.trim() || null,
          end: end.trim() || null,
          room: room.trim(),
          attendee_ids: ids,
        }),
      );
      onAdded(detail.meetings.find((m) => !before.has(m.id))?.id ?? null);
      reset();
      setOpen(false);
    } catch (err) {
      const message = errorMessage(err);
      const field = timeFieldOf(message);
      if (field) {
        setTimeError({ field, message });
        timeRefs[field].current?.focus();
      } else {
        setError(message);
      }
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <Button ref={toggleRef} onClick={expand} icon={<Plus className="size-4" aria-hidden="true" />} className="mt-4">
        Add meeting
      </Button>
    );
  }

  const active = (roster ?? []).filter((a) => a.active);
  return (
    <form onSubmit={submit} noValidate aria-labelledby={`${id}-title`} className="mt-4 rounded-lg border border-line bg-white p-4">
      <h2 id={`${id}-title`} className="font-heading text-[15px] font-bold text-navy">
        Add a meeting
      </h2>
      <p className="mt-0.5 text-[13px] text-muted">For a row the PDF missed. It starts as a draft; verify it like the others.</p>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-6">
        <label className="col-span-2 sm:col-span-3">
          <span className={fieldLabelClass}>Company</span>
          <input
            ref={companyRef}
            value={company}
            onChange={(e) => {
              setCompany(e.target.value);
              setError(null);
            }}
            aria-invalid={error && !company.trim() ? true : undefined}
            placeholder="e.g. Northwind Robotics"
            className={`${inputClass} h-9 font-semibold`}
          />
        </label>
        <label className="col-span-2 sm:col-span-3">
          <span className={fieldLabelClass}>Room</span>
          <input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="e.g. Salon 4" className={`${inputClass} h-9 font-semibold`} />
        </label>
        <div className="col-span-2">
          <label htmlFor={`${id}-date`} className={fieldLabelClass}>
            Date
          </label>
          <DateSelect
            id={`${id}-date`}
            value={date || null}
            dates={dates}
            other={otherDate}
            onSelect={(choice) => {
              if (choice === OTHER_DATE) {
                setOtherDate(true);
                requestAnimationFrame(() => otherRef.current?.focus());
              } else {
                setOtherDate(false);
                setDate(choice);
              }
            }}
          />
          {otherDate && <OtherDateInput id={`${id}-other`} inputRef={otherRef} value={date} onChange={setDate} />}
        </div>
        {(["start", "end"] as const).map((field) => {
          const value = field === "start" ? start : end;
          const problem = timeError?.field === field ? timeError.message : null;
          return (
            <div key={field} className="sm:col-span-2">
              <label htmlFor={`${id}-${field}`} className={fieldLabelClass}>
                {field === "start" ? "Start" : "End"}
              </label>
              <input
                ref={timeRefs[field]}
                id={`${id}-${field}`}
                value={value}
                autoComplete="off"
                placeholder={field === "start" ? "e.g. 2:30 PM" : "Optional, e.g. 3:15 PM"}
                aria-invalid={problem ? true : undefined}
                aria-describedby={problem ? `${id}-${field}-error` : undefined}
                onChange={(e) => {
                  (field === "start" ? setStart : setEnd)(e.target.value);
                  if (timeError?.field === field) setTimeError(null);
                }}
                className={`${inputClass} tabular h-9 font-semibold`}
              />
              {problem && (
                <p id={`${id}-${field}-error`} role="alert" className="mt-1 text-xs font-semibold text-red">
                  {problem}
                </p>
              )}
            </div>
          );
        })}
      </div>
      <fieldset className="mt-3">
        <legend className={fieldLabelClass}>Colleagues</legend>
        <div className="flex flex-wrap gap-1.5">
          {roster === null && <span className="text-[13px] text-muted">Loading the roster…</span>}
          {active.map((a) => {
            const on = ids.includes(a.id);
            return (
              <label
                key={a.id}
                className={[
                  "inline-flex h-7 cursor-pointer select-none items-center gap-1 rounded-full border px-2.5 text-[13px] font-semibold",
                  "transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-navy",
                  on ? "border-navy-2 bg-navy-2 text-white" : "border-line bg-white text-ink hover:border-line-strong hover:bg-cream",
                ].join(" ")}
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={on}
                  onChange={() => setIds((cur) => (cur.includes(a.id) ? cur.filter((x) => x !== a.id) : [...cur, a.id]))}
                />
                {on && <Check className="size-3.5" strokeWidth={2.5} aria-hidden="true" />}
                {a.name}
              </label>
            );
          })}
        </div>
      </fieldset>
      {error && (
        <p role="alert" className="mt-3 text-[13px] font-semibold text-red">
          {error}
        </p>
      )}
      <div className="mt-4 flex gap-2.5">
        <Button type="submit" variant="primary" loading={saving}>
          Add meeting
        </Button>
        <Button
          onClick={() => {
            reset();
            setOpen(false);
          }}
          disabled={saving}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
