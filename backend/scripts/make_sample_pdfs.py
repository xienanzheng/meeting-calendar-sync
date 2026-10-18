"""Generate synthetic broker schedule PDFs and their expected extraction JSON into samples/.

Every company, person, broker and hotel here is fictional.
Run from backend/: uv run python scripts/make_sample_pdfs.py
"""
import datetime as dt
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
FOOTER = "Sample data — fictional companies and people"
STYLES = getSampleStyleSheet()
SMALL = ParagraphStyle("small", parent=STYLES["Normal"], fontSize=8, leading=10)
COMPACT = ParagraphStyle("compact", parent=STYLES["Normal"], fontSize=9, leading=11)

ROSTER = [
    {"name": "Avery Kim", "email": "avery.kim@example.com", "aliases": []},
    {"name": "Sam Patel", "email": "sam.patel@example.com", "aliases": ["Samir Patel"]},
    {"name": "Jordan Lee", "email": "jordan.lee@example.com", "aliases": []},
    {"name": "Riley Chen", "email": "riley.chen@example.com", "aliases": []},
    {"name": "Morgan Diaz", "email": "morgan.diaz@example.com", "aliases": []},
    {"name": "Taylor Brooks", "email": "taylor.brooks@example.com", "aliases": ["Tay Brooks"]},
]


def mt(date, start, end, fmt, room, company, ticker, execs, firm, page):
    return {"date": date, "start": start, "end": end, "room": room, "company": company, "ticker": ticker,
            "format": fmt, "company_attendees": execs, "firm_attendees": firm, "notes": None, "page": page}


BROKER_A = {
    "conference_name": "Industrials Conference 2026", "broker": "Example Securities",
    "hotel": "The Example Grand Hotel", "city": "New York, NY", "timezone": "America/New_York",
    "schedule_for": "Sample Capital",
    "meetings": [
        mt("2026-11-10", "08:00", "08:45", "one_on_one", "Salon 4", "Northwind Robotics", "NWRB", ["Dana Shore, CFO"], ["Avery Kim", "Jordan Lee"], 1),
        mt("2026-11-10", "09:00", "09:45", "one_on_one", "Suite 1201", "Borealis Grid Systems", "BRGS", ["Tom Rayner, CEO", "Ellen Ko, Investor Relations"], ["Jordan Lee"], 1),
        mt("2026-11-10", "10:00", "10:45", "one_on_one", "Salon 4", "Cobalt Freight Lines", "CBFL", ["Priya Nair, CFO"], ["Riley Chen", "Avery Kim"], 1),
        mt("2026-11-10", "11:00", "11:45", "group", "Suite 1410", "Halcyon Aerostructures", "HLAS", ["Marcus Webb, CEO"], ["Taylor Brooks"], 1),
        mt("2026-11-10", "12:00", "13:15", "meal", "Grand Ballroom B", "Keystone Valve Corp", "KSVC", ["Lena Ortiz, CFO"], ["Avery Kim", "Jordan Lee", "Riley Chen"], 1),
        mt("2026-11-10", "13:30", "14:15", "one_on_one", "TBD", "Meridian Rail Holdings", "MRHL", ["Owen Pratt, CFO"], ["Morgan Diaz"], 1),
        mt("2026-11-11", "08:00", "08:45", "one_on_one", "Salon 2", "Ironleaf Packaging", "IRLP", ["Grace Liu, CEO"], ["Sam Patel"], 2),
        mt("2026-11-11", "09:00", "09:45", "group", "Salon 2", "Quarry Point Materials", "QPMT", ["Victor Hale, CFO"], ["Sam Patel", "Taylor Brooks"], 2),
        mt("2026-11-11", "10:00", "10:45", "one_on_one", "Suite 1201", "Tidewater Pumps", "TWPM", ["Nina Brandt, Investor Relations"], ["Chris Wong"], 2),
        mt("2026-11-11", "11:00", "11:45", "one_on_one", "Suite 1201", "Summit Forge Industries", "SMFI", ["Ray Castillo, CEO"], ["Avery Kim"], 2),
        mt("2026-11-11", "14:00", "14:45", "one_on_one", "Salon 4", "Lumen Sensor Works", "LMSW", ["Hana Mori, CFO"], ["Jordan Lee"], 2),
        mt("2026-11-11", "15:00", "15:45", "group", "Salon 4", "Granite Bay Logistics", "GBLG", ["Eli Turner, CFO"], ["Morgan Diaz", "Riley Chen"], 2),
    ],
}

BROKER_B = {
    "conference_name": "Technology Summit 2026", "broker": "Demo Partners Securities",
    "hotel": "The Demo Resort", "city": "Las Vegas, NV", "timezone": "America/Los_Angeles",
    "schedule_for": "Sample Capital",
    "meetings": [
        mt("2026-12-02", "08:30", "09:15", "one_on_one", "Suite 3105", "Vantage Cloud Software", "VTCS", ["Ari Feld, CEO"], ["A. Kim"], 1),
        mt("2026-12-02", "09:30", "10:30", "group", "Ballroom C", "Pixelmint Studios", "PXMS", ["June Park, CFO"], ["A. Kim", "Rilay Chen"], 1),
        mt("2026-12-02", "09:45", "10:30", "one_on_one", "Suite 2210", "Orbital Data Networks", "ORDN", ["Sol Mendes, CFO"], ["Rilay Chen"], 1),
        mt("2026-12-02", "12:00", "13:30", "meal", "Sage Room", "Brightpath Payments", "BRPY", ["Kim Alvarez, CEO", "Rob Tan, CFO"], ["Morgan D.", "Tay Brooks"], 1),
        mt("2026-12-03", "08:00", "08:45", "one_on_one", "Suite 3105", "Kestrel Security", "KSTL", ["Ivan Petrov, CFO"], ["Jordan Lee"], 2),
        mt("2026-12-03", "09:00", "09:45", "one_on_one", "Suite 3105", "Nimbus Health Tech", "NBHT", ["Clara Voss, CEO"], ["Samir Patel"], 2),
        mt("2026-12-03", "10:00", "11:00", "group", "Ballroom A", "Driftwood Semiconductors", "DWSC", ["Ken Ito, CFO"], ["Jordan Lee", "Samir Patel", "A. Kim"], 2),
        mt("2026-12-03", "13:00", "13:45", "one_on_one", "Suite 2210", "Copperline Telecom", "CPLT", ["Maya Ross, Investor Relations"], ["Tay Brooks"], 2),
    ],
}

BROKER_C = {
    "conference_name": "Global Healthcare Conference 2026", "broker": "Demo Bank",
    "hotel": "The Sample Park Hotel", "city": "London", "timezone": "Europe/London",
    "schedule_for": "Sam Patel",
    "meetings": [
        mt("2026-11-17", "08:00", None, "meal", "Garden Room", "Asterion Biologics", "ASTB", ["Dr. Helen Marsh, CEO"], [], 1),
        mt("2026-11-17", "09:30", None, "one_on_one", "Suite 502", "Corvid Diagnostics", "CRVD", ["Paul Okafor, CFO"], [], 1),
        mt("2026-11-17", "11:00", None, "group", "Churchill Room", "Elmstone Pharma", "ELMP", ["Sofia Reyes, CFO", "Tim Hart, Investor Relations"], [], 1),
        mt("2026-11-17", "14:00", None, "one_on_one", "Suite 502", "Juniper MedDevices", "JNMD", ["Arun Mehta, CEO"], [], 1),
        mt("2026-11-18", "09:00", None, "one_on_one", "Suite 610", "Larkspur Genomics", "LKGN", ["Beth Collins, CFO"], [], 1),
        mt("2026-11-18", "10:30", None, "one_on_one", "Suite 610", "Mossgate Therapeutics", "MSGT", ["Omar Haddad, CEO"], [], 1),
    ],
}

A_TYPE = {"one_on_one": "1x1", "group": "Group", "meal": "Lunch"}
B_TYPE = {"one_on_one": "1x1", "group": "Group", "meal": "Lunch"}
C_TYPE = {"one_on_one": "1x1", "group": "Group", "meal": "Breakfast"}


def h12(hhmm: str, compact: bool = False) -> str:
    h, m = map(int, hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    text = f"{h % 12 or 12}:{m:02d}"
    return f"{text}{suffix.lower()}" if compact else f"{text} {suffix}"


def us_heading(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d:%A, %B} {d.day}, {d.year}"


def uk_heading(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d:%A} {d.day} {d:%B %Y}"


def _doc(path: Path) -> SimpleDocTemplate:
    return SimpleDocTemplate(str(path), pagesize=letter, invariant=1, title="Sample broker schedule",
                             leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)


def _table(rows, widths) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDDDDD")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    return table


def _header(lines: list[str]) -> list:
    story = [Paragraph(lines[0], STYLES["Title"])]
    story += [Paragraph(line, STYLES["Normal"]) for line in lines[1:]]
    return story + [Spacer(1, 10)]


def build_a(out: Path) -> None:
    d = BROKER_A
    story = _header([d["conference_name"], f"Hosted by {d['broker']}", f"{d['hotel']} · {d['city']}",
                     "November 10–11, 2026", f"Meeting schedule for: {d['schedule_for']}"])
    for i, day in enumerate(["2026-11-10", "2026-11-11"]):
        if i:
            story.append(PageBreak())
        story.append(Paragraph(us_heading(day), STYLES["Heading2"]))
        rows = [["Time", "Type", "Room", "Company (Ticker)", "Management", "Attendees"]]
        for m in (x for x in d["meetings"] if x["date"] == day):
            rows.append([f"{h12(m['start'])} - {h12(m['end'])}", A_TYPE[m["format"]], m["room"],
                         Paragraph(f"{m['company']} ({m['ticker']})", SMALL),
                         Paragraph("; ".join(m["company_attendees"]), SMALL),
                         Paragraph(", ".join(m["firm_attendees"]), SMALL)])
        story += [_table(rows, [85, 40, 70, 120, 120, 97]), Spacer(1, 12), Paragraph(FOOTER, SMALL)]
    _doc(out / "broker_a_grid.pdf").build(story)


def build_b(out: Path) -> None:
    d = BROKER_B
    story = _header([d["conference_name"], f"Hosted by {d['broker']}", f"{d['hotel']} · {d['city']}",
                     "December 2–3, 2026", f"Schedule for: {d['schedule_for']}"])
    for i, m in enumerate(d["meetings"]):
        if i == 4:
            story += [Paragraph(FOOTER, SMALL), PageBreak()]
        day = dt.date.fromisoformat(m["date"])
        story.append(Paragraph(f"<b>{m['company']} ({m['ticker']})</b>", STYLES["Heading4"]))
        for line in (f"Format: {B_TYPE[m['format']]}", f"Date: {day:%A, %B} {day.day}",
                     f"Time: {h12(m['start'], True)}-{h12(m['end'], True)}", f"Location: {m['room']}",
                     f"Company: {'; '.join(m['company_attendees'])}", f"Attendees: {', '.join(m['firm_attendees'])}"):
            story.append(Paragraph(line, COMPACT))
        story.append(Spacer(1, 6))
    story.append(Paragraph(FOOTER, SMALL))
    _doc(out / "broker_b_by_company.pdf").build(story)


def build_c(out: Path) -> None:
    d = BROKER_C
    story = _header([d["conference_name"], f"Hosted by {d['broker']}", f"{d['hotel']} · {d['city']}",
                     "17–18 November 2026", f"Itinerary for: {d['schedule_for']}"])
    for day in ["2026-11-17", "2026-11-18"]:
        story.append(Paragraph(uk_heading(day), STYLES["Heading2"]))
        rows = [["Time", "Meeting", "Company", "Location", "With"]]
        for m in (x for x in d["meetings"] if x["date"] == day):
            rows.append([m["start"], C_TYPE[m["format"]], Paragraph(f"{m['company']} ({m['ticker']})", SMALL),
                         m["room"], Paragraph("; ".join(m["company_attendees"]), SMALL)])
        story += [_table(rows, [50, 60, 150, 100, 172]), Spacer(1, 10)]
    story.append(Paragraph(FOOTER, SMALL))
    _doc(out / "broker_c_itinerary.pdf").build(story)


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main(out: Path = SAMPLES) -> None:
    out.mkdir(parents=True, exist_ok=True)
    build_a(out)
    build_b(out)
    build_c(out)
    for name, data in (("broker_a_grid", BROKER_A), ("broker_b_by_company", BROKER_B), ("broker_c_itinerary", BROKER_C)):
        _write_json(out / f"{name}.expected.json", data)
    _write_json(out / "roster.sample.json", ROSTER)


if __name__ == "__main__":
    main()
