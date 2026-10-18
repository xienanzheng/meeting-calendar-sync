import { ChevronDown, CircleAlert, FileUp, Search } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { errorMessage, type ConferenceDetail } from "../../api";
import { dateRange, tzLabel, tzShort } from "../../lib/format";
import { checkPdf } from "../../lib/upload";
import { Button } from "../Button";
import { EditableCell } from "../EditableCell";
import { fieldLabelClass, inputClass } from "../fields";
import { Popover } from "../Popover";

let zones: string[] | null = null;
function allZones(): string[] {
  if (!zones) {
    try {
      zones = Intl.supportedValuesOf("timeZone");
    } catch {
      zones = ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "Europe/London", "Asia/Hong_Kong"];
    }
  }
  return zones;
}

function TimezonePicker({ timezone, onSave }: { timezone: string | null; onSave: (tz: string) => Promise<void> }) {
  const anchor = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLSelectElement>(null);
  const [query, setQuery] = useState("");
  const [choice, setChoice] = useState(timezone ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const popId = "tz-picker";

  const matches = useMemo(() => {
    const words = query.toLowerCase().replace(/\s+/g, "_").split(/[_/]+/).filter(Boolean);
    const list = allZones().filter((z) => words.every((w) => z.toLowerCase().includes(w)));
    return choice && !list.includes(choice) ? [choice, ...list] : list;
  }, [query, choice]);

  function close() {
    document.getElementById(popId)?.hidePopover();
  }

  async function save() {
    if (!choice || choice === timezone) return close();
    setSaving(true);
    setError(null);
    try {
      await onSave(choice);
      close();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button
        ref={anchor}
        type="button"
        popoverTarget={popId}
        className={`inline-flex shrink-0 items-center gap-1 rounded-sm underline decoration-white/35 underline-offset-[3px] transition-colors duration-150 hover:decoration-white ${timezone ? "" : "font-bold text-red-on-navy decoration-red-on-navy/50"}`}
      >
        {!timezone && <CircleAlert className="size-3.5" aria-hidden="true" />}
        {timezone ? (
          <>
            {/* Below 1366px the bar is tight: "ET", as the table's local-time hints write it. */}
            <span className="max-[1366px]:sr-only">{tzLabel(timezone)}</span>
            <span aria-hidden="true" title={tzLabel(timezone)} className="min-[1366px]:hidden">
              {tzShort(timezone)}
            </span>
          </>
        ) : (
          "Set timezone"
        )}
        <ChevronDown className="size-3" aria-hidden="true" />
        <span className="sr-only">, change the conference timezone</span>
      </button>
      <Popover
        id={popId}
        anchor={anchor}
        label="Conference timezone"
        width={360}
        onOpenChange={(open) => {
          if (open) {
            setQuery("");
            setChoice(timezone ?? "");
            setError(null);
            search.current?.focus();
            // Start the list at the current zone rather than at Africa/Abidjan.
            requestAnimationFrame(() => list.current?.querySelector("option:checked")?.scrollIntoView({ block: "center" }));
          }
        }}
      >
        <form
          className="p-4"
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <h2 className="font-heading text-[15px] font-bold text-navy">Conference timezone</h2>
          <p className="mt-1 text-[13px] text-muted">
            The hotel's zone. Every meeting time is read in it, so changing it moves verified meetings on colleagues'
            calendars.
          </p>
          <label className="mt-3 block">
            <span className={fieldLabelClass}>Search</span>
            <span className="relative block">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted" aria-hidden="true" />
              <input
                ref={search}
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="City or region, e.g. New York"
                className={`${inputClass} h-9 pl-8`}
              />
            </span>
          </label>
          <label className="mt-2 block">
            <span className="sr-only">Timezone</span>
            <select
              ref={list}
              size={8}
              value={choice}
              onChange={(event) => setChoice(event.target.value)}
              onDoubleClick={() => save()}
              className={`${inputClass} tabular py-1`}
            >
              {matches.map((z) => (
                <option key={z} value={z} className="rounded-sm px-1.5 py-0.5 checked:bg-select checked:text-navy">
                  {z.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </label>
          {matches.length === 0 && <p className="mt-1 text-xs text-muted">No timezone matches “{query}”.</p>}
          {error && (
            <p role="alert" className="mt-2 text-xs font-semibold text-red">
              {error}
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <Button type="submit" variant="primary" size="sm" loading={saving} disabled={!choice}>
              {choice ? `Use ${tzLabel(choice)}` : "Pick a timezone"}
            </Button>
            <Button size="sm" onClick={close}>
              Cancel
            </Button>
          </div>
        </form>
      </Popover>
    </>
  );
}

/**
 * The conference in the top bar: its name (click to rename) with the revision number, then hotel · city ·
 * dates · timezone, and the "Upload revised PDF" button.
 */
export function ConferenceContext({
  detail,
  uploading,
  onRename,
  onTimezone,
  onUploadRevision,
  onUploadProblem,
}: {
  detail: ConferenceDetail;
  uploading: boolean;
  onRename: (name: string) => Promise<void>;
  onTimezone: (tz: string) => Promise<void>;
  onUploadRevision: (file: File) => void;
  onUploadProblem: (message: string) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const place = [detail.hotel, detail.city].filter((part) => part.trim()).join(" · ");
  return (
    <>
      <div className="min-w-0 max-w-[560px]">
        {/* The revision tag rides on the name line, where the name can truncate to make room; the line
            under it (hotel, dates, timezone) is the one that runs out of space in a laptop-width bar. */}
        <div className="flex min-w-0 items-center gap-2">
          <div className="min-w-0 has-[input]:flex-1">
            <EditableCell
              tone="navy"
              value={detail.name}
              label="conference name"
              placeholder="Untitled conference"
              textClassName="font-heading text-[17px] font-semibold leading-snug"
              validate={(value) => (value.trim() ? null : "Enter a name for the conference.")}
              onSave={(name) => onRename(name.trim())}
            />
          </div>
          {detail.revision_number > 1 && (
            <span className="shrink-0 whitespace-nowrap rounded-sm bg-navy-2 px-1.5 py-0.5 text-[11px] font-semibold leading-none text-white/85">
              Revision {detail.revision_number}
            </span>
          )}
        </div>
        <div className="flex min-w-0 items-center gap-1.5 whitespace-nowrap text-xs font-medium text-white/75 max-[1280px]:gap-1">
          {place && (
            <>
              {/* Truncates, but never below ~18 characters ("The Demo Resort · L…"), so the hotel stays readable. */}
              <span className="min-w-[8rem] truncate" title={place}>
                {place}
              </span>
              <span aria-hidden="true">·</span>
            </>
          )}
          <span className="tabular shrink-0">{dateRange(detail.first_date, detail.last_date)}</span>
          <span aria-hidden="true">·</span>
          <TimezonePicker timezone={detail.timezone} onSave={onTimezone} />
        </div>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (!file) return;
          const problem = checkPdf(file);
          if (problem) onUploadProblem(problem);
          else onUploadRevision(file);
        }}
      />
      <Button
        variant="ghost"
        size="sm"
        loading={uploading}
        onClick={() => fileRef.current?.click()}
        icon={<FileUp className="size-3.5" aria-hidden="true" />}
        title="Upload the broker's revised schedule; you review what changed before anything moves"
        className="max-[1920px]:w-8 max-[1920px]:px-0"
      >
        <span className="max-[1920px]:sr-only">{uploading ? "Reading the PDF…" : "Upload revised PDF"}</span>
      </Button>
    </>
  );
}
