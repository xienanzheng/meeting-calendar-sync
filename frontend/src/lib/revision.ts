import type { FieldValue, Revision, RevisionChange } from "../api";
import { dayHeading, formatLabel, formatTime12, shortDate } from "./format";

// The fields a broker revision compares (backend/mcs/revisions.py COMPARED_FIELDS), in CR's words.
const FIELD_LABELS: Record<string, string> = {
  date: "Date",
  start: "Start",
  end: "End",
  room: "Room",
  format: "Format",
  ticker: "Ticker",
  company: "Company",
  company_attendees: "Executives",
  firm_attendees: "Colleagues",
};

/** "firm_attendees" -> "Colleagues"; unknown fields read as plain words. */
export function fieldLabel(field: string): string {
  if (FIELD_LABELS[field]) return FIELD_LABELS[field];
  const words = field.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** One side of a before → after pair, formatted the way the timetable shows it; empty reads "—". */
export function formatValue(field: string, value: FieldValue): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (!value.trim()) return "—";
  switch (field) {
    case "start":
    case "end":
      return formatTime12(value);
    case "date":
      return dayHeading(value);
    case "format":
      return formatLabel(value);
    default:
      return value;
  }
}

/** Every change starts accepted; CR unticks the ones she doesn't want. */
export function defaultAccepted(revision: Pick<Revision, "changes">): Set<string> {
  return new Set(revision.changes.map((c) => c.id));
}

/** A new set with `id` flipped; the input set is left alone. */
export function toggleAccepted(set: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/**
 * The server's one-line summary without the company (the row already shows it), with 24h times and
 * ISO dates in the timetable's format: "Cobalt Freight Lines: time 10:00–10:45 → 14:30–15:15"
 * -> "Time 10:00 AM–10:45 AM → 2:30 PM–3:15 PM".
 */
export function readableSummary(change: Pick<RevisionChange, "company" | "summary">): string {
  let text = change.summary.trim();
  for (const prefix of [`${change.company}:`, `New: ${change.company}`, `Dropped: ${change.company}`]) {
    if (text.startsWith(prefix)) {
      text = text.slice(prefix.length).trim();
      break;
    }
  }
  text = text
    .replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (iso) => shortDate(iso))
    .replace(/\b([01]?\d|2[0-3]):([0-5]\d)\b/g, (hhmm) => formatTime12(hhmm));
  return text.charAt(0).toUpperCase() + text.slice(1);
}
