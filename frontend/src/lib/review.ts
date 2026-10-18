import type { Attendee, ConferenceDetail, Counts, Meeting, Severity } from "../api";

export type Selection = { kind: "all" } | { kind: "colleague"; id: number } | { kind: "unmatched"; name: string };
export type StatusFilter = "all" | "needs_attention" | "ready" | "verified" | "sent";
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
  return meetings.filter((m) => inSelection(m, selection) && (status === "all" || m.review_state === status));
}

/** Counts for the status chips; cancelled meetings are not counted anywhere. */
export function statusCounts(meetings: Meeting[]): Record<StatusFilter, number> {
  const counts: Record<StatusFilter, number> = { all: 0, needs_attention: 0, ready: 0, verified: 0, sent: 0 };
  for (const m of meetings.filter(isLive)) {
    counts.all += 1;
    if (m.review_state in counts) counts[m.review_state as StatusFilter] += 1;
  }
  return counts;
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
      if (meeting.attendees.some((a) => a.sync === "changed")) return { label: "CHANGED — RESEND", tone: "amber" };
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
