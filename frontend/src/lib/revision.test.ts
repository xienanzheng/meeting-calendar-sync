import { describe, expect, it } from "vitest";
import type { Revision } from "../api";
import { defaultAccepted, fieldLabel, formatValue, toggleAccepted } from "./revision";

const rev = { id: 7, number: 2, pdf_filename: "v2.pdf", created_at: "2026-11-03T10:00:00", unchanged_count: 8,
  changes: [{ id: "c1" }, { id: "c2" }, { id: "c3" }] } as unknown as Revision;

describe("revision helpers", () => {
  it("accepts every change by default and toggles", () => {
    const all = defaultAccepted(rev);
    expect([...all]).toEqual(["c1", "c2", "c3"]);
    const less = toggleAccepted(all, "c2");
    expect([...less]).toEqual(["c1", "c3"]);
    expect([...toggleAccepted(less, "c2")].sort()).toEqual(["c1", "c2", "c3"]);
    expect([...all]).toEqual(["c1", "c2", "c3"]); // not mutated
  });
  it("labels and formats fields", () => {
    expect(fieldLabel("firm_attendees")).toBe("Colleagues");
    expect(fieldLabel("company_attendees")).toBe("Executives");
    expect(fieldLabel("start")).toBe("Start");
    expect(formatValue("start", "14:30")).toBe("2:30 PM");
    expect(formatValue("date", "2026-11-11")).toBe("Wednesday, November 11");
    expect(formatValue("firm_attendees", ["Taylor Brooks", "Jordan Lee"])).toBe("Taylor Brooks, Jordan Lee");
    expect(formatValue("room", null)).toBe("—");
    expect(formatValue("format", "one_on_one")).toBe("1x1");
  });
});
