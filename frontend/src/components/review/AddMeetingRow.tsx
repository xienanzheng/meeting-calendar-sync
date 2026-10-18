import { Check, Plus } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { addMeeting, errorMessage, type Analyst, type ConferenceDetail } from "../../api";
import { Button } from "../Button";
import { fieldLabelClass, inputClass } from "../fields";

/**
 * "Add meeting" under the timetable: collapsed to one quiet button, it opens an inline form for a
 * meeting the PDF missed. The new meeting starts as a draft like any other.
 */
export function AddMeetingRow({
  cid,
  knownIds,
  roster,
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
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [room, setRoom] = useState("");
  const [ids, setIds] = useState<number[]>(defaultColleague ? [defaultColleague] : []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const companyRef = useRef<HTMLInputElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const opened = useRef(false);

  useEffect(() => {
    if (open && opened.current) companyRef.current?.focus();
    if (!open && opened.current) toggleRef.current?.focus();
  }, [open]);

  function expand() {
    opened.current = true;
    setDate(defaultDate ?? "");
    setIds(defaultColleague ? [defaultColleague] : []);
    setError(null);
    setOpen(true);
  }

  function reset() {
    setCompany("");
    setStart("");
    setEnd("");
    setRoom("");
    setError(null);
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
    try {
      const before = new Set(knownIds);
      const detail = await run(
        addMeeting(cid, {
          company: company.trim(),
          date: date || null,
          start: start || null,
          end: end || null,
          room: room.trim(),
          attendee_ids: ids,
        }),
      );
      onAdded(detail.meetings.find((m) => !before.has(m.id))?.id ?? null);
      reset();
      setOpen(false);
    } catch (err) {
      setError(errorMessage(err));
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
        <label className="col-span-2">
          <span className={fieldLabelClass}>Date</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`${inputClass} tabular h-9 font-semibold`} />
        </label>
        <label>
          <span className={fieldLabelClass}>Start</span>
          <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={`${inputClass} tabular h-9 font-semibold`} />
        </label>
        <label>
          <span className={fieldLabelClass}>End</span>
          <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className={`${inputClass} tabular h-9 font-semibold`} />
        </label>
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
