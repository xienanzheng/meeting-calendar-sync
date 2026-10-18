import { describe, expect, it } from "vitest";
import { readableSummary } from "./revision";

describe("readableSummary", () => {
  it("drops the company and reads times and dates the timetable way", () => {
    expect(readableSummary({ company: "Cobalt Freight Lines", summary: "Cobalt Freight Lines: time 10:00–10:45 → 14:30–15:15" }))
      .toBe("Time 10:00 AM–10:45 AM → 2:30 PM–3:15 PM");
    expect(readableSummary({ company: "Atlas Rail Systems", summary: "New: Atlas Rail Systems on 2026-11-11 at 16:00" }))
      .toBe("On Wed, Nov 11 at 4:00 PM");
    expect(readableSummary({ company: "Tidewater Pumps", summary: "Dropped: Tidewater Pumps on 2026-11-11 at 10:00" }))
      .toBe("On Wed, Nov 11 at 10:00 AM");
    expect(readableSummary({ company: "Meridian Rail", summary: "Meridian Rail: room TBD → Suite 1505" })).toBe("Room TBD → Suite 1505");
  });
});
