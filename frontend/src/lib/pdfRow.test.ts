import { describe, expect, it } from "vitest";
import { findRowBox as find, type PdfTextItem, type RowBox } from "./pdfRow";

/** The box rounded to 0.01pt, so float noise in the union doesn't fail an exact comparison. */
function findRowBox(items: PdfTextItem[], company: string, ticker: string | null): RowBox | null {
  const box = find(items, company, ticker);
  if (!box) return null;
  const r = (v: number) => Math.round(v * 100) / 100;
  return { left: r(box.left), right: r(box.right), bottom: r(box.bottom), top: r(box.top) };
}

/** A synthetic pdf.js text item: `str` drawn at (x, baseline) in PDF user space (y grows upwards). */
const item = (str: string, x: number, baseline: number, width: number, height = 10): PdfTextItem => ({
  str,
  transform: [height, 0, 0, height, x, baseline],
  width,
  height,
});

// Broker B prints one block per company (heading, then Format/Date/Time/... lines).
const byCompany = [
  item("Technology Summit 2026", 200, 740, 160, 14),
  item("Vantage Cloud Software (VTCS)", 40, 680, 150),
  item("Format: 1x1", 40, 668, 60),
  item("Pixelmint Studios (PXMS)", 40, 600, 130),
  item("Format: Group", 40, 588, 70),
  item("Attendees: A. Kim, Riley Chen", 40, 540, 150),
  item("Orbital Data Networks (ORDN)", 40, 500, 150),
];

describe("findRowBox", () => {
  it("finds a company printed on its own", () => {
    const items = [item("Header", 40, 700, 60), item("Pixelmint Studios", 50, 600, 100), item("Group", 50, 588, 40)];
    expect(findRowBox(items, "Pixelmint Studios", null)).toEqual({ left: 50, right: 150, bottom: 597.5, top: 608.5 });
  });

  it("finds a company printed with its ticker in parentheses, ignoring case and punctuation", () => {
    expect(findRowBox(byCompany, "pixelmint studios", "PXMS")).toEqual({ left: 40, right: 170, bottom: 597.5, top: 608.5 });
  });

  it("falls back to the ticker when the company is printed differently", () => {
    const box = findRowBox(byCompany, "Orbital Data Networks, Inc.", "ORDN");
    expect(box).toEqual({ left: 40, right: 190, bottom: 497.5, top: 508.5 });
  });

  it("returns null when neither the company nor the ticker is on the page", () => {
    expect(findRowBox(byCompany, "Keystone Valve Corp", "KSVC")).toBeNull();
    // A ticker only matches a whole word, so "ORB" is not found inside "Orbital".
    expect(findRowBox(byCompany, "Orb Holdings", "ORB")).toBeNull();
    expect(findRowBox(byCompany, "", null)).toBeNull();
  });

  it("unions every item on the matched row's baseline, and nothing above or below it", () => {
    // Broker A's grid: one printed row is six cells; the last cell wraps onto a second line.
    const grid = [
      item("11:00 AM - 11:45 AM", 40, 515, 70, 8),
      item("Halcyon Aerostructures (HLAS)", 260, 515, 120, 8),
      item("12:00 PM - 1:15 PM", 40, 500, 70, 8),
      item("Lunch", 120, 500, 22, 8),
      item("Grand Ballroom B", 170, 500, 64, 8),
      item("Keystone Valve Corp (KSVC)", 260, 500.6, 110, 8), // a slightly different baseline in the same row
      item("Lena Ortiz, CFO", 400, 500, 60, 8),
      item("Avery Kim, Jordan Lee,", 480, 500, 90, 8),
      item("Riley Chen", 480, 490, 40, 8),
    ];
    expect(findRowBox(grid, "Keystone Valve Corp", "KSVC")).toEqual({ left: 40, right: 570, bottom: 498, top: 507.4 });
  });

  it("matches a company split across several items on one line", () => {
    const items = [item("Keystone Valve", 260, 500, 60, 8), item("Corp (KSVC)", 322, 500, 48, 8), item("Lunch", 120, 500, 22, 8)];
    expect(findRowBox(items, "Keystone Valve Corp", null)).toEqual({ left: 120, right: 370, bottom: 498, top: 506.8 });
  });
});
