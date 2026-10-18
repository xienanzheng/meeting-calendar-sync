import { describe, expect, it } from "vitest";
import { dateRange, dayHeading, formatTime12, localHint, tzLabel } from "./format";

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
