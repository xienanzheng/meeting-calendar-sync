import { Search } from "lucide-react";
import { useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { errorMessage } from "../../api";
import { tzLabel, zoneMatches } from "../../lib/format";
import { Button } from "../Button";
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

/**
 * The timezone chooser shared by the conference (top bar) and a single meeting (source panel): search by
 * city, pick from the list, save. `reset` adds a second way out, e.g. "Use the conference timezone".
 * Opened by the caller's own button with `popoverTarget={id}`.
 */
export function TimezonePopover({
  id,
  anchor,
  title,
  description,
  current,
  onSave,
  reset,
}: {
  id: string;
  anchor: RefObject<HTMLElement | null>;
  title: string;
  description: ReactNode;
  current: string | null;
  onSave: (tz: string) => Promise<void>;
  reset?: { label: string; onReset: () => Promise<void> };
}) {
  const search = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLSelectElement>(null);
  const [query, setQuery] = useState("");
  const [choice, setChoice] = useState(current ?? "");
  const [saving, setSaving] = useState<"save" | "reset" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const matches = useMemo(() => zoneMatches(query, allZones(), choice), [query, choice]);

  function close() {
    document.getElementById(id)?.hidePopover();
  }

  async function act(kind: "save" | "reset", work: () => Promise<void>) {
    setSaving(kind);
    setError(null);
    try {
      await work();
      close();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(null);
    }
  }

  function save() {
    if (!choice || choice === current) return close();
    act("save", () => onSave(choice));
  }

  return (
    <Popover
      id={id}
      anchor={anchor}
      label={title}
      width={360}
      onOpenChange={(open) => {
        if (open) {
          setQuery("");
          setChoice(current ?? "");
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
        <h2 className="font-heading text-[15px] font-bold text-navy">{title}</h2>
        <p className="mt-1 text-[13px] text-muted">{description}</p>
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
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="submit" variant="primary" size="sm" loading={saving === "save"} disabled={!choice || saving !== null}>
            {choice ? `Use ${tzLabel(choice)}` : "Pick a timezone"}
          </Button>
          {reset && (
            <Button size="sm" loading={saving === "reset"} disabled={saving !== null} onClick={() => act("reset", reset.onReset)}>
              {reset.label}
            </Button>
          )}
          <Button size="sm" onClick={close}>
            Cancel
          </Button>
        </div>
      </form>
    </Popover>
  );
}
