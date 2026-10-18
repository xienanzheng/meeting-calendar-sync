import { ChevronDown, Loader2, Plus, X } from "lucide-react";
import { useState } from "react";
import { errorMessage, type Analyst, type Attendee } from "../../api";
import { fieldLabelClass } from "../fields";

const MATCH_NOTES: Record<string, string> = {
  alias: "matched by alias",
  initial: "matched by initials",
  fuzzy: "matched by similar spelling",
  manual: "added by hand",
  default: "default colleague",
};

/**
 * The meeting's colleagues as removable chips, plus an "Add colleague" select of active roster colleagues
 * not already on it. `onChange` saves the new id list and rejects with the server's error.
 */
export function AttendeePicker({
  attendees,
  roster,
  disabled = false,
  onChange,
}: {
  attendees: Attendee[];
  roster: Analyst[] | null;
  disabled?: boolean;
  onChange: (ids: number[]) => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ids = attendees.map((a) => a.analyst_id);
  const available = (roster ?? []).filter((a) => a.active && !ids.includes(a.id));

  async function save(next: number[]) {
    setSaving(true);
    setError(null);
    try {
      await onChange(next);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <fieldset disabled={disabled || saving} aria-busy={saving || undefined}>
      <legend className={fieldLabelClass}>Colleagues</legend>
      <div className="flex flex-wrap items-center gap-1.5">
        {attendees.length === 0 && <span className="text-[13px] font-semibold text-red">No colleague yet</span>}
        {attendees.map((a) => (
          <span
            key={a.analyst_id}
            title={MATCH_NOTES[a.match] ? `${a.name}, ${MATCH_NOTES[a.match]}` : a.name}
            className={`inline-flex h-7 items-center gap-1 rounded-full border pl-2.5 pr-1 text-[13px] font-semibold ${a.match === "fuzzy" ? "border-amber-line bg-amber-bg text-amber" : "border-line bg-cream text-ink"}`}
          >
            {a.name}
            <button
              type="button"
              onClick={() => save(ids.filter((id) => id !== a.analyst_id))}
              aria-label={`Remove ${a.name}`}
              className="grid size-5 place-items-center rounded-full text-muted transition-colors duration-150 hover:bg-white hover:text-red disabled:cursor-not-allowed"
            >
              <X className="size-3.5" aria-hidden="true" />
            </button>
          </span>
        ))}
        {available.length > 0 && (
          <span className="relative inline-flex">
            <Plus className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-blue" aria-hidden="true" />
            <select
              value=""
              aria-label="Add colleague"
              onChange={(event) => {
                const id = Number(event.target.value);
                if (id) save([...ids, id]);
              }}
              className="h-7 cursor-pointer appearance-none rounded-full border border-dashed border-line-strong bg-white pl-6 pr-7 text-[13px] font-semibold text-blue transition-colors duration-150 hover:border-blue hover:bg-cream disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">Add colleague</option>
              {available.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-blue" aria-hidden="true" />
          </span>
        )}
        {saving && <Loader2 className="size-3.5 animate-spin text-muted" aria-label="Saving colleagues" />}
      </div>
      {roster === null && <p className="mt-1 text-xs text-muted">Loading the roster…</p>}
      {error && (
        <p role="alert" className="mt-1 text-xs font-semibold text-red">
          {error}
        </p>
      )}
    </fieldset>
  );
}
