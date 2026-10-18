import { ChevronDown } from "lucide-react";
import type { KeyboardEvent, ReactNode, Ref } from "react";
import { dayHeading } from "../../lib/format";
import { inputClass } from "../fields";

/** The select's value for "Other date…". */
export const OTHER_DATE = "other";

/**
 * A meeting date as one of the conference's days, written like the day headings ("Wednesday,
 * December 2") so no browser locale can turn Dec 2 into 02/12, plus "Other date…" for a day outside
 * the conference. `onSelect` gets a "YYYY-MM-DD" date or OTHER_DATE. Used by the source panel (which
 * saves on pick) and the add-meeting form (which saves on submit).
 */
export function DateSelect({
  id,
  value,
  dates,
  other,
  disabled,
  invalid,
  onSelect,
}: {
  id: string;
  value: string | null;
  /** The conference's days (`conferenceDates`); `value` is added when it falls outside them. */
  dates: string[];
  /** True while "Other date…" is chosen and its date input is showing. */
  other: boolean;
  disabled?: boolean;
  invalid?: boolean;
  onSelect: (choice: string) => void;
}) {
  const options = value && !dates.includes(value) ? [...dates, value].sort() : dates;
  return (
    <span className="relative block">
      <select
        id={id}
        value={other ? OTHER_DATE : (value ?? "")}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        onChange={(event) => onSelect(event.target.value)}
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
  );
}

/**
 * The date input "Other date…" reveals, with the date it reads spelled out under it: the native
 * field follows the browser's locale (09/12/2026 may be 9 December), the line under it does not.
 */
export function OtherDateInput({
  id,
  inputRef,
  value,
  disabled,
  action,
  onChange,
  onKeyDown,
}: {
  id: string;
  inputRef?: Ref<HTMLInputElement>;
  value: string;
  disabled?: boolean;
  /** A button beside the input, e.g. the source panel's "Use date". */
  action?: ReactNode;
  onChange: (value: string) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void;
}) {
  return (
    <div className="mt-2">
      <div className="flex gap-2">
        <label htmlFor={id} className="sr-only">
          Other date
        </label>
        <input
          ref={inputRef}
          id={id}
          type="date"
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          className={`${inputClass} tabular h-9 font-semibold`}
        />
        {action}
      </div>
      {value && (
        <p className="mt-1 text-xs font-medium text-muted">
          {dayHeading(value)}, {value.slice(0, 4)}
        </p>
      )}
    </div>
  );
}
