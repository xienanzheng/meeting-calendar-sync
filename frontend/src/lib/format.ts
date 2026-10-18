import { DateTime } from "luxon";

const LOCALE = "en-US";

// Short labels the coordinator reads at a glance; any other zone falls back to luxon's abbreviation.
const ZONE_ABBR: Record<string, string> = {
  "America/Los_Angeles": "PT",
  "America/Denver": "MT",
  "America/Chicago": "CT",
  "America/New_York": "ET",
  "Europe/London": "UK",
  "Asia/Hong_Kong": "HKT",
  "Asia/Tokyo": "JT",
  "Asia/Singapore": "SGT",
};

/** "13:30" -> "1:30 PM"; null -> "—". */
export function formatTime12(hhmm: string | null): string {
  if (!hhmm) return "—";
  const match = /^(\d{1,2}):(\d{2})/.exec(hhmm);
  if (!match) return hhmm;
  const hours = Number(match[1]);
  const suffix = hours < 12 ? "AM" : "PM";
  return `${hours % 12 || 12}:${match[2]} ${suffix}`;
}

/**
 * The viewer's own clock time for a hotel-local meeting time, e.g. "5:00 AM PT" or "6:00 PM PT, day before".
 * Null when the two zones share an offset at that instant, or when date, time or hotel zone is missing.
 */
export function localHint(
  date: string | null,
  hhmm: string | null,
  hotelTz: string | null,
  viewerTz: string,
): string | null {
  if (!date || !hhmm || !hotelTz || !viewerTz) return null;
  const hotel = DateTime.fromISO(`${date}T${hhmm}`, { zone: hotelTz });
  if (!hotel.isValid) return null;
  const viewer = hotel.setZone(viewerTz);
  if (!viewer.isValid || viewer.offset === hotel.offset) return null;
  const abbr = ZONE_ABBR[viewerTz] ?? viewer.setLocale(LOCALE).toFormat("ZZZZ");
  const hotelDay = hotel.toISODate() ?? "";
  const viewerDay = viewer.toISODate() ?? "";
  const shift = viewerDay < hotelDay ? ", day before" : viewerDay > hotelDay ? ", next day" : "";
  return `${formatTime12(viewer.toFormat("HH:mm"))} ${abbr}${shift}`;
}

function parseDate(iso: string | null): DateTime | null {
  if (!iso) return null;
  const parsed = DateTime.fromISO(iso, { locale: LOCALE });
  return parsed.isValid ? parsed : null;
}

/** "2026-11-10" -> "Tuesday, November 10"; null -> "Date missing". */
export function dayHeading(isoDate: string | null): string {
  const day = parseDate(isoDate);
  return day ? day.toFormat("cccc, LLLL d") : "Date missing";
}

/** "ET" for America/New_York, the short names the local-time hints use; else an offset name like "GMT+5:30". */
export function tzShort(tz: string | null): string {
  if (!tz) return "No timezone";
  if (ZONE_ABBR[tz]) return ZONE_ABBR[tz];
  const now = DateTime.now().setZone(tz);
  return now.isValid ? now.setLocale(LOCALE).toFormat("ZZZZ") : tz;
}

/** "Eastern time" for America/New_York; the raw zone name when Intl can't name it. */
export function tzLabel(tz: string | null): string {
  if (!tz) return "Timezone not set";
  try {
    const parts = new Intl.DateTimeFormat(LOCALE, { timeZone: tz, timeZoneName: "longGeneric" }).formatToParts(new Date());
    const name = parts.find((p) => p.type === "timeZoneName")?.value;
    return name ? name.replace(/ Time$/, " time") : tz;
  } catch {
    return tz;
  }
}

/** "Nov 10–11, 2026", "Nov 30 – Dec 2, 2026", "Nov 10, 2026"; "Dates unknown" when both are missing. */
export function dateRange(first: string | null, last: string | null): string {
  const a = parseDate(first) ?? parseDate(last);
  const b = parseDate(last) ?? a;
  if (!a || !b) return "Dates unknown";
  const [start, end] = a <= b ? [a, b] : [b, a];
  if (start.hasSame(end, "day")) return start.toFormat("LLL d, yyyy");
  if (start.hasSame(end, "month")) return `${start.toFormat("LLL d")}–${end.toFormat("d, yyyy")}`;
  if (start.hasSame(end, "year")) return `${start.toFormat("LLL d")} – ${end.toFormat("LLL d, yyyy")}`;
  return `${start.toFormat("LLL d, yyyy")} – ${end.toFormat("LLL d, yyyy")}`;
}

/** The viewer's IANA zone, e.g. "America/Los_Angeles". */
export function viewerZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** 184320 -> "180 KB", 2621440 -> "2.5 MB"; for the selected-file line on the upload card. */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const FORMAT_LABELS: Record<string, string> = { one_on_one: "1x1", group: "Group", meal: "Meal", other: "Meeting" };

/** "one_on_one" -> "1x1"; the same labels the calendar entries use. */
export function formatLabel(format: string): string {
  return FORMAT_LABELS[format] ?? format;
}

/** "2026-11-11" -> "Wed, Nov 11"; the raw text when it isn't a date. */
export function shortDate(isoDate: string): string {
  const day = parseDate(isoDate);
  return day ? day.toFormat("ccc, LLL d") : isoDate;
}

/** "Avery Kim" -> "AK", "Chris" -> "CH"; for the colleague rail avatars. */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}
