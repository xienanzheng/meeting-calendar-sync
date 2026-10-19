import { describe, expect, it } from "vitest";
import { dateRange, dayHeading, formatTime12, localHint, meetingZone, tzLabel, tzShort, zoneMatches, zoneTag } from "./format";

describe("formatTime12", () => {
  it.each([
    ["08:00", "8:00 AM"], ["13:30", "1:30 PM"], ["12:00", "12:00 PM"], ["00:15", "12:15 AM"], [null, "—"],
  ])("%s -> %s", (input, out) => expect(formatTime12(input)).toBe(out));
});

describe("localHint", () => {
  it("shows the viewer's time when zones differ", () => {
    expect(localHint("2026-11-10", "08:00", "America/New_York", "America/Los_Angeles")).toBe("5:00 AM PT");
  });
  it("marks a day shift", () => {
    expect(localHint("2026-11-17", "08:00", "Europe/London", "America/Los_Angeles")).toBe("12:00 AM PT");
    expect(localHint("2026-11-17", "02:00", "Europe/London", "America/Los_Angeles")).toBe("6:00 PM PT, day before");
  });
  it("is null when the offset is the same or data is missing", () => {
    expect(localHint("2026-11-10", "08:00", "America/New_York", "America/New_York")).toBeNull();
    expect(localHint("2026-11-10", "08:00", "America/New_York", "America/Toronto")).toBeNull();
    expect(localHint(null, "08:00", "America/New_York", "America/Los_Angeles")).toBeNull();
    expect(localHint("2026-11-10", "08:00", null, "America/Los_Angeles")).toBeNull();
  });
});

describe("dates", () => {
  it("formats headings and ranges", () => {
    expect(dayHeading("2026-11-10")).toBe("Tuesday, November 10");
    expect(dayHeading(null)).toBe("Date missing");
    expect(dateRange("2026-11-10", "2026-11-11")).toBe("Nov 10–11, 2026");
    expect(dateRange("2026-11-30", "2026-12-02")).toBe("Nov 30 – Dec 2, 2026");
    expect(dateRange("2026-11-10", "2026-11-10")).toBe("Nov 10, 2026");
    expect(dateRange(null, null)).toBe("Dates unknown");
  });
  it("labels timezones", () => {
    expect(tzLabel("America/New_York")).toBe("Eastern time");
    expect(tzLabel(null)).toBe("Timezone not set");
  });
});

describe("tzShort", () => {
  it("uses the same short names as the local-time hints", () => {
    expect(tzShort("America/New_York")).toBe("ET");
    expect(tzShort("America/Los_Angeles")).toBe("PT");
    expect(tzShort("Asia/Hong_Kong")).toBe("HKT");
  });
  it("falls back to an offset name, and copes with no zone", () => {
    expect(tzShort("Asia/Kolkata")).toMatch(/^(GMT\+5:30|IST)$/);
    expect(tzShort(null)).toBe("No timezone");
  });
});

describe("meetingZone", () => {
  it("uses the meeting's own zone, else the conference's", () => {
    expect(meetingZone({ timezone: "America/Chicago" }, "America/New_York")).toBe("America/Chicago");
    expect(meetingZone({ timezone: null }, "America/New_York")).toBe("America/New_York");
    expect(meetingZone({ timezone: null }, null)).toBeNull();
  });
});

describe("zoneTag", () => {
  it("names a meeting's zone only when it differs from the conference's", () => {
    expect(zoneTag("America/Chicago", "America/New_York")).toBe("CT");
    expect(zoneTag("America/New_York", "America/New_York")).toBeNull();
    expect(zoneTag(null, "America/New_York")).toBeNull();
    expect(zoneTag("Asia/Tokyo", null)).toBe("JT");
  });
  it("names an offset as it is on the meeting's date, not today", () => {
    expect(zoneTag("Europe/Paris", "America/New_York", "2026-11-10")).toBe("GMT+1");
    expect(zoneTag("Europe/Paris", "America/New_York", "2026-07-10")).toBe("GMT+2");
  });
});

describe("zoneMatches", () => {
  const zones = ["America/Chicago", "America/New_York", "Asia/Tokyo", "Europe/London"];
  it("matches city words in any order, ignoring case and spaces", () => {
    expect(zoneMatches("new york", zones)).toEqual(["America/New_York"]);
    expect(zoneMatches("YORK america", zones)).toEqual(["America/New_York"]);
    expect(zoneMatches("", zones)).toEqual(zones);
    expect(zoneMatches("paris", zones)).toEqual([]);
  });
  it("keeps the current choice visible even when the search hides it", () => {
    expect(zoneMatches("tokyo", zones, "Europe/London")).toEqual(["Europe/London", "Asia/Tokyo"]);
    expect(zoneMatches("tokyo", zones, "Asia/Tokyo")).toEqual(["Asia/Tokyo"]);
  });
});
