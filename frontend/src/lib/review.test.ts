import { describe, expect, it } from "vitest";
import type { Attendee, ConferenceDetail, Meeting } from "../api";
import { colleaguesIn, filterMeetings, groupByDate, sendLabel, sharedWith, stampFor, statusCounts, unmatchedNames } from "./review";

const att = (id: number, name: string, sync: Attendee["sync"] = "not_sent") =>
  ({ analyst_id: id, name, email: `${name.split(" ")[0].toLowerCase()}@example.com`, match: "exact", sync, sync_error: null });

function m(id: number, over: Partial<Meeting> = {}): Meeting {
  return {
    id, conference_id: 1, date: "2026-11-10", start: "09:00", end: "09:45", end_assumed: false, room: "Salon 4",
    company: `Co ${id}`, ticker: null, format: "one_on_one", company_attendees: [], raw_attendee_names: [],
    ignored_names: [], unmatched_names: [], notes: "", source_page: 1, status: "draft", review_state: "ready",
    attendees: [att(1, "Avery Kim")], removed: [], flags: [], ...over,
  } as Meeting;
}

const meetings = [
  m(1, { start: "10:00" }),
  m(2, { start: "08:00", attendees: [att(1, "Avery Kim"), att(3, "Jordan Lee")], review_state: "verified", status: "confirmed" }),
  m(3, { date: "2026-11-11", attendees: [], review_state: "needs_attention",
         flags: [{ code: "no_attendee", severity: "block", message: "x" }, { code: "unmatched_name", severity: "warn", message: "y" }],
         unmatched_names: ["Chris Wong"] }),
  m(4, { date: null, start: null, review_state: "needs_attention", flags: [{ code: "missing_date", severity: "block", message: "x" }] }),
  m(5, { review_state: "cancelled", status: "cancelled", start: "11:00" }),
  m(6, { start: "12:00", attendees: [att(3, "Jordan Lee", "sent")], review_state: "sent", status: "confirmed",
         flags: [{ code: "double_booked", severity: "warn", message: "z" }] }),
];
const detail = { meetings } as unknown as ConferenceDetail;

describe("groupByDate", () => {
  it("groups by date, missing date last, sorted by start", () => {
    const groups = groupByDate(meetings);
    expect(groups.map((g) => g.date)).toEqual(["2026-11-10", "2026-11-11", null]);
    expect(groups[0].meetings.map((x) => x.id)).toEqual([2, 1, 5, 6]);
  });
});

describe("colleagues and unmatched", () => {
  it("lists colleagues with counts and worst flag, ignoring cancelled meetings", () => {
    expect(colleaguesIn(detail)).toEqual([
      { id: 1, name: "Avery Kim", email: "avery@example.com", count: 3, worst: "block" },
      { id: 3, name: "Jordan Lee", email: "jordan@example.com", count: 2, worst: "warn" },
    ]);
  });
  it("aggregates unmatched names", () => {
    expect(unmatchedNames(detail)).toEqual([{ name: "Chris Wong", count: 1 }]);
  });
});

describe("filterMeetings and counts", () => {
  it("filters by colleague, unmatched name and status", () => {
    expect(filterMeetings(meetings, { kind: "colleague", id: 3 }, "all").map((x) => x.id)).toEqual([2, 6]);
    expect(filterMeetings(meetings, { kind: "unmatched", name: "Chris Wong" }, "all").map((x) => x.id)).toEqual([3]);
    expect(filterMeetings(meetings, { kind: "all" }, "needs_attention").map((x) => x.id)).toEqual([3, 4]);
    expect(filterMeetings(meetings, { kind: "all" }, "all").map((x) => x.id)).toContain(5);
  });
  it("counts statuses without cancelled", () => {
    expect(statusCounts(meetings)).toEqual({ all: 5, needs_attention: 2, ready: 1, verified: 1, sent: 1 });
  });
});

describe("stamps and labels", () => {
  it.each([
    [m(1), "DRAFT", "muted"],
    [m(4, { review_state: "needs_attention", flags: [{ code: "missing_date", severity: "block", message: "" }] }), "NEEDS DATE", "red"],
    [m(7, { review_state: "needs_attention", flags: [{ code: "missing_time", severity: "block", message: "" }] }), "NEEDS TIME", "red"],
    [m(8, { review_state: "needs_attention", flags: [{ code: "no_attendee", severity: "block", message: "" }] }), "NEEDS COLLEAGUE", "red"],
    [m(9, { review_state: "needs_attention", flags: [{ code: "no_timezone", severity: "block", message: "" }] }), "NEEDS TIMEZONE", "red"],
    [m(10, { review_state: "needs_attention", flags: [{ code: "end_before_start", severity: "block", message: "" }] }), "CHECK TIME", "red"],
    [m(11, { review_state: "verified" }), "VERIFIED", "navy"],
    [m(12, { review_state: "verified", attendees: [att(1, "Avery Kim", "changed")] }), "CHANGED", "amber"],
    [m(13, { review_state: "verified", attendees: [att(1, "Avery Kim", "failed")] }), "FAILED", "red"],
    [m(14, { review_state: "sent" }), "SENT", "green"],
    [m(15, { review_state: "cancelled" }), "CANCELLED", "struck"],
  ])("stamp %#", (meeting, label, tone) => expect(stampFor(meeting as Meeting)).toEqual({ label, tone }));

  it("shared-with excludes the selected colleague", () => {
    expect(sharedWith(meetings[1], { kind: "colleague", id: 1 })).toEqual(["Jordan Lee"]);
    expect(sharedWith(meetings[1], { kind: "all" })).toEqual(["Avery Kim", "Jordan Lee"]);
  });

  it("send label", () => {
    expect(sendLabel({ pending_actions: 29 } as never)).toBe("Send 29 to calendars");
    expect(sendLabel({ pending_actions: 1 } as never)).toBe("Send 1 to calendars");
    expect(sendLabel({ pending_actions: 0 } as never)).toBe("Nothing to send");
  });
});
