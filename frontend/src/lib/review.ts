import type { Attendee, ConferenceDetail, Counts, Meeting, Severity } from "../api";

export type Selection = { kind: "all" } | { kind: "colleague"; id: number } | { kind: "unmatched"; name: string };
/** A review state chip, or "warnings": live meetings carrying any warn flag, whatever their state. */
export type StatusFilter = "all" | "needs_attention" | "ready" | "verified" | "sent" | "warnings";
/** The chips that count review states (`statusCounts`); "warnings" is counted by `warningCount`. */
export type StateFilter = Exclude<StatusFilter, "warnings">;
export type StampTone = "muted" | "red" | "navy" | "amber" | "green" | "struck";

export interface Stamp {
  label: string;
  tone: StampTone;
}

export interface DayGroup {
  date: string | null;
  meetings: Meeting[];
}

export interface ColleagueEntry {
  id: number;
  name: string;
  email: string;
  count: number;
  worst: Severity | null;
}

export interface UnmatchedEntry {
  name: string;
  count: number;
}

const isLive = (m: Meeting) => m.review_state !== "cancelled";
const hasWarning = (m: Meeting) => isLive(m) && m.flags.some((f) => f.severity === "warn");

/** Nulls sort after every value. */
function compareNullable(a: string | null, b: string | null): number {
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return a < b ? -1 : 1;
}

function byTime(a: Meeting, b: Meeting): number {
  return compareNullable(a.start, b.start) || a.company.localeCompare(b.company) || a.id - b.id;
}

/** Day groups in date order with "date missing" last; meetings inside a day by start time, then company. */
export function groupByDate(meetings: Meeting[]): DayGroup[] {
  const byDate = new Map<string | null, Meeting[]>();
  for (const m of meetings) {
    const list = byDate.get(m.date) ?? [];
    list.push(m);
    byDate.set(m.date, list);
  }
  return [...byDate.keys()]
    .sort(compareNullable)
    .map((date) => ({ date, meetings: [...(byDate.get(date) ?? [])].sort(byTime) }));
}

/** Everyone whose calendar this meeting touches: current attendees plus colleagues being taken off it. */
function touched(m: Meeting): Attendee[] {
  return [...m.attendees, ...m.removed];
}

function worstSeverity(current: Severity | null, m: Meeting): Severity | null {
  if (current === "block" || m.flags.some((f) => f.severity === "block")) return "block";
  if (current === "warn" || m.flags.some((f) => f.severity === "warn")) return "warn";
  return null;
}

/**
 * The colleagues on this conference's live meetings, by name, with how many meetings each has
 * and the most serious flag among them. Counts match what the colleague's filtered view shows.
 */
export function colleaguesIn(detail: Pick<ConferenceDetail, "meetings">): ColleagueEntry[] {
  const out = new Map<number, ColleagueEntry>();
  for (const m of detail.meetings.filter(isLive)) {
    const seen = new Set<number>();
    for (const a of touched(m)) {
      if (seen.has(a.analyst_id)) continue;
      seen.add(a.analyst_id);
      const entry = out.get(a.analyst_id) ?? { id: a.analyst_id, name: a.name, email: a.email, count: 0, worst: null };
      entry.count += 1;
      entry.worst = worstSeverity(entry.worst, m);
      out.set(a.analyst_id, entry);
    }
  }
  return [...out.values()].sort((a, b) => a.name.localeCompare(b.name) || a.id - b.id);
}

/** Printed names that didn't match the roster, with how many live meetings mention each. */
export function unmatchedNames(detail: Pick<ConferenceDetail, "meetings">): UnmatchedEntry[] {
  const counts = new Map<string, number>();
  for (const m of detail.meetings.filter(isLive)) {
    for (const name of new Set(m.unmatched_names)) counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => a.name.localeCompare(b.name));
}

function inSelection(m: Meeting, selection: Selection): boolean {
  switch (selection.kind) {
    case "all":
      return true;
    case "colleague":
      return touched(m).some((a) => a.analyst_id === selection.id);
    case "unmatched":
      return m.unmatched_names.includes(selection.name);
  }
}

/**
 * Meetings for the rail selection and status chip, in input order. Status "all" keeps cancelled
 * meetings so they can be shown struck through; nothing disappears from a colleague's view.
 */
export function filterMeetings(meetings: Meeting[], selection: Selection, status: StatusFilter): Meeting[] {
  const matches = (m: Meeting) =>
    status === "all" ? true : status === "warnings" ? hasWarning(m) : m.review_state === status;
  return meetings.filter((m) => inSelection(m, selection) && matches(m));
}

/** Counts for the status chips; cancelled meetings are not counted anywhere. */
export function statusCounts(meetings: Meeting[]): Record<StateFilter, number> {
  const counts: Record<StateFilter, number> = { all: 0, needs_attention: 0, ready: 0, verified: 0, sent: 0 };
  for (const m of meetings.filter(isLive)) {
    counts.all += 1;
    if (m.review_state in counts) counts[m.review_state as StateFilter] += 1;
  }
  return counts;
}

/** How many live meetings carry at least one warning (the "Warnings" chip). */
export function warningCount(meetings: Meeting[]): number {
  return meetings.filter(hasWarning).length;
}

const DAY_MS = 24 * 60 * 60 * 1000;
const MAX_SPAN_DAYS = 31;

/**
 * The dates a meeting of this conference can move to: every day from its first to its last date
 * (for spans up to a month), plus any meeting's date outside that, in order. "YYYY-MM-DD" strings.
 */
export function conferenceDates(
  detail: Pick<ConferenceDetail, "first_date" | "last_date"> & { meetings: Pick<Meeting, "date">[] },
): string[] {
  const out = new Set<string>();
  const ends = [detail.first_date, detail.last_date].filter((d): d is string => !!d).sort();
  if (ends.length) {
    const from = Date.parse(`${ends[0]}T00:00:00Z`);
    const to = Date.parse(`${ends[ends.length - 1]}T00:00:00Z`);
    if (!Number.isNaN(from) && !Number.isNaN(to) && (to - from) / DAY_MS <= MAX_SPAN_DAYS) {
      for (let t = from; t <= to; t += DAY_MS) out.add(new Date(t).toISOString().slice(0, 10));
    } else {
      ends.forEach((d) => out.add(d));
    }
  }
  for (const m of detail.meetings) if (m.date) out.add(m.date);
  return [...out].sort();
}

const NEEDS_LABELS: Record<string, string> = {
  missing_date: "NEEDS DATE",
  missing_time: "NEEDS TIME",
  no_attendee: "NEEDS COLLEAGUE",
  no_timezone: "NEEDS TIMEZONE",
  end_before_start: "CHECK TIME",
};

/** The status stamp a meeting row wears. */
export function stampFor(meeting: Meeting): Stamp {
  switch (meeting.review_state) {
    case "cancelled":
      return { label: "CANCELLED", tone: "struck" };
    case "needs_attention": {
      const block = meeting.flags.find((f) => f.severity === "block");
      return { label: (block && NEEDS_LABELS[block.code]) || "NEEDS ATTENTION", tone: "red" };
    }
    case "ready":
      return { label: "DRAFT", tone: "muted" };
    case "verified":
      if (touched(meeting).some((a) => a.sync === "failed")) return { label: "FAILED", tone: "red" };
      // Calendars sync on every approval, so a changed entry is simply on its way (SyncStatus says why if not).
      if (meeting.attendees.some((a) => a.sync === "changed")) return { label: "CHANGED", tone: "amber" };
      return { label: "VERIFIED", tone: "navy" };
    case "sent":
      return { label: "SENT", tone: "green" };
  }
}

/** The other colleagues on a meeting, leaving out the one whose itinerary is being viewed. */
export function sharedWith(meeting: Meeting, selection: Selection): string[] {
  return meeting.attendees
    .filter((a) => !(selection.kind === "colleague" && a.analyst_id === selection.id))
    .map((a) => a.name);
}

/** Label for the beige send button in the top bar. */
export function sendLabel(counts: Pick<Counts, "pending_actions">): string {
  return counts.pending_actions > 0 ? `Send ${counts.pending_actions} to calendars` : "Nothing to send";
}

/** "all", "c:12", "u:Chris Wong": one string per rail entry, for the select and for comparing. */
export function selectionKey(selection: Selection): string {
  switch (selection.kind) {
    case "all":
      return "all";
    case "colleague":
      return `c:${selection.id}`;
    case "unmatched":
      return `u:${selection.name}`;
  }
}

/** The inverse of `selectionKey`. */
export function selectionFromKey(key: string): Selection {
  if (key.startsWith("c:")) return { kind: "colleague", id: Number(key.slice(2)) };
  if (key.startsWith("u:")) return { kind: "unmatched", name: key.slice(2) };
  return { kind: "all" };
}

/** True when some colleague's calendar already holds this meeting, so deleting it cancels instead. */
export function isOnCalendars(meeting: Meeting): boolean {
  return touched(meeting).some((a) => a.sync === "sent" || a.sync === "changed" || a.sync === "failed");
}
