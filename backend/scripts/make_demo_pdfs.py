"""Generate a demo pack of 8 broker schedule PDFs into samples/demo/.

Every company, person, broker and hotel is fictional. Layouts, cities, timezones and colleagues
vary so a demo shows how Claude copes with different broker formats.
Run from backend/: uv run python scripts/make_demo_pdfs.py
"""
import copy
import datetime as dt
import json
import random
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parents[2] / "samples" / "demo"
FOOTER = "Sample data — fictional companies and people"
ST = getSampleStyleSheet()
SMALL = ParagraphStyle("small", parent=ST["Normal"], fontSize=8, leading=10)
BODY = ParagraphStyle("body", parent=ST["Normal"], fontSize=9, leading=11.5)

ROSTER = [
    {"name": "Avery Kim", "email": "avery.kim@example.com", "aliases": []},
    {"name": "Sam Patel", "email": "sam.patel@example.com", "aliases": ["Samir Patel"]},
    {"name": "Jordan Lee", "email": "jordan.lee@example.com", "aliases": []},
    {"name": "Riley Chen", "email": "riley.chen@example.com", "aliases": []},
    {"name": "Morgan Diaz", "email": "morgan.diaz@example.com", "aliases": []},
    {"name": "Taylor Brooks", "email": "taylor.brooks@example.com", "aliases": ["Tay Brooks"]},
    {"name": "Priya Shah", "email": "priya.shah@example.com", "aliases": []},
    {"name": "Daniel Okafor", "email": "daniel.okafor@example.com", "aliases": ["Dan Okafor"]},
]

# How a colleague's name may be printed by different brokers (initials, aliases, one typo).
PRINTED = {
    "Avery Kim": ["Avery Kim", "A. Kim"],
    "Sam Patel": ["Sam Patel", "Samir Patel"],
    "Jordan Lee": ["Jordan Lee", "J. Lee"],
    "Riley Chen": ["Riley Chen", "Rilay Chen"],
    "Morgan Diaz": ["Morgan Diaz", "Morgan D."],
    "Taylor Brooks": ["Taylor Brooks", "Tay Brooks"],
    "Priya Shah": ["Priya Shah", "Priya S."],
    "Daniel Okafor": ["Daniel Okafor", "D. Okafor"],
}

FIRST = ["Ava", "Ben", "Carla", "Dev", "Elena", "Felix", "Grace", "Hugo", "Isla", "Jonah", "Keiko", "Liam",
         "Maya", "Nikhil", "Olga", "Pablo", "Quinn", "Rosa", "Stefan", "Tara", "Umar", "Vera", "Wes", "Yuki"]
LAST = ["Abbott", "Brennan", "Castillo", "Dunmore", "Ellery", "Fontaine", "Grieve", "Halvorsen", "Ibarra",
        "Jaskolski", "Kowal", "Lindqvist", "Marchetti", "Nakamura", "Oyelaran", "Pryce", "Quist", "Rourke",
        "Sorensen", "Tanaka", "Underhill", "Varga", "Whitlock", "Zeller"]
TITLES = ["CEO", "CFO", "CFO", "Investor Relations", "COO", "Head of Strategy"]


def execs(rng: random.Random, n: int) -> list[str]:
    return [f"{rng.choice(FIRST)} {rng.choice(LAST)}, {rng.choice(TITLES)}" for _ in range(n)]


def printed(rng: random.Random, names: list[str]) -> list[str]:
    return [rng.choice(PRINTED[n]) if n in PRINTED else n for n in names]


def mt(date, start, end, fmt, room, company, ticker, execs_, firm, page):
    return {"date": date, "start": start, "end": end, "room": room, "company": company, "ticker": ticker,
            "format": fmt, "company_attendees": execs_, "firm_attendees": firm, "notes": None, "page": page}


def plus(hhmm: str, minutes: int) -> str:
    t = dt.datetime.strptime(hhmm, "%H:%M") + dt.timedelta(minutes=minutes)
    return t.strftime("%H:%M")


def h12(hhmm: str, compact: bool = False) -> str:
    h, m = map(int, hhmm.split(":"))
    text = f"{h % 12 or 12}:{m:02d}"
    suffix = "AM" if h < 12 else "PM"
    return f"{text}{suffix.lower()}" if compact else f"{text} {suffix}"


def heading(iso: str, uk: bool = False) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d:%A} {d.day} {d:%B %Y}" if uk else f"{d:%A, %B} {d.day}, {d.year}"


def schedule(rng, companies, days, colleagues, rooms, slots, *, per_slot=1, meal_slot=None, pages=None):
    """Build meetings: one or more per slot per day; colleagues drawn from `colleagues`."""
    meetings, queue = [], list(companies)
    for di, day in enumerate(days):
        for start, length in slots:
            for _ in range(per_slot):
                if not queue:
                    return meetings
                name, ticker = queue.pop(0)
                fmt = "meal" if start == meal_slot else rng.choice(["one_on_one", "one_on_one", "one_on_one", "group"])
                firm = rng.sample(colleagues, k=rng.choice([1, 1, 2, 2, 3]) if fmt != "meal" else 3)
                meetings.append(mt(day, start, plus(start, length), fmt, rng.choice(rooms), name, ticker,
                                   execs(rng, rng.choice([1, 1, 2])), printed(rng, firm),
                                   (pages or {}).get(di, di + 1)))
    return meetings


def doc(path: Path) -> SimpleDocTemplate:
    return SimpleDocTemplate(str(path), pagesize=letter, invariant=1, title="Broker schedule",
                             leftMargin=40, rightMargin=40, topMargin=36, bottomMargin=36)


def table(rows, widths) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDDDDD")),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    return t


def header(lines: list[str]) -> list:
    return [Paragraph(lines[0], ST["Title"])] + [Paragraph(x, ST["Normal"]) for x in lines[1:]] + [Spacer(1, 8)]


TYPE = {"one_on_one": "1x1", "group": "Group", "meal": "Lunch", "other": "Site visit"}


def render_grid(path, ev, *, h24=False):
    story = header([ev["conference_name"], f"Hosted by {ev['broker']}", f"{ev['hotel']} · {ev['city']}",
                    ev["dates_line"]] + ([ev["note"]] if ev.get("note") else []) +
                   [f"Meeting schedule for: {ev['schedule_for']}"])
    days = sorted({m["date"] for m in ev["meetings"]})
    for i, day in enumerate(days):
        if i:
            story.append(PageBreak())
        story.append(Paragraph(heading(day), ST["Heading2"]))
        rows = [["Time", "Type", "Room", "Company (Ticker)", "Management", "Attendees"]]
        for m in sorted((x for x in ev["meetings"] if x["date"] == day), key=lambda x: x["start"]):
            when = f"{m['start']}-{m['end']}" if h24 else f"{h12(m['start'])} - {h12(m['end'])}"
            rows.append([when, TYPE[m["format"]], m["room"], Paragraph(f"{m['company']} ({m['ticker']})", SMALL),
                         Paragraph("; ".join(m["company_attendees"]), SMALL),
                         Paragraph(", ".join(m["firm_attendees"]), SMALL)])
        story += [table(rows, [85, 40, 70, 120, 120, 97]), Spacer(1, 10), Paragraph(FOOTER, SMALL)]
    doc(path).build(story)


def render_sections(path, ev):
    story = header([ev["conference_name"], f"Hosted by {ev['broker']}", f"{ev['hotel']} · {ev['city']}",
                    ev["dates_line"], f"Schedule for: {ev['schedule_for']}"])
    current_page = 1
    for m in ev["meetings"]:
        if m["page"] != current_page:
            story += [Paragraph(FOOTER, SMALL), PageBreak()]
            current_page = m["page"]
        d = dt.date.fromisoformat(m["date"])
        story.append(Paragraph(f"<b>{m['company']} ({m['ticker']})</b>", ST["Heading4"]))
        for line in (f"Format: {TYPE[m['format']]}", f"Date: {d:%A, %B} {d.day}",
                     f"Time: {h12(m['start'], True)}-{h12(m['end'], True)}", f"Location: {m['room']}",
                     f"Company: {'; '.join(m['company_attendees'])}", f"Attendees: {', '.join(m['firm_attendees'])}"):
            story.append(Paragraph(line, BODY))
        story.append(Spacer(1, 5))
    story.append(Paragraph(FOOTER, SMALL))
    doc(path).build(story)


def render_itinerary(path, ev):
    story = header([ev["conference_name"], f"Hosted by {ev['broker']}", f"{ev['hotel']} · {ev['city']}",
                    ev["dates_line"], f"Itinerary for: {ev['schedule_for']}"])
    for day in sorted({m["date"] for m in ev["meetings"]}):
        story.append(Paragraph(heading(day, uk=True), ST["Heading2"]))
        rows = [["Time", "Meeting", "Company", "Location", "With"]]
        for m in (x for x in ev["meetings"] if x["date"] == day):
            rows.append([m["start"], TYPE[m["format"]].replace("Lunch", "Lunch"),
                         Paragraph(f"{m['company']} ({m['ticker']})", SMALL), m["room"],
                         Paragraph("; ".join(m["company_attendees"]), SMALL)])
        story += [table(rows, [50, 60, 150, 100, 172]), Spacer(1, 8)]
    story.append(Paragraph(FOOTER, SMALL))
    doc(path).build(story)


def render_list(path, ev):
    story = header([ev["conference_name"], f"Organised by {ev['broker']}", f"Venue: {ev['hotel']}, {ev['city']}",
                    ev["dates_line"], f"Client: {ev['schedule_for']}"])
    days = sorted({m["date"] for m in ev["meetings"]})
    for i, day in enumerate(days):
        if i:
            story.append(PageBreak())
        story.append(Paragraph(heading(day, uk=True), ST["Heading2"]))
        for m in sorted((x for x in ev["meetings"] if x["date"] == day), key=lambda x: x["start"]):
            story.append(Paragraph(
                f"<b>{m['start']}–{m['end']}</b> · {m['room']} · {TYPE[m['format']]} — "
                f"<b>{m['company']}</b> ({m['ticker']}) — {'; '.join(m['company_attendees'])}<br/>"
                f"<i>Attending:</i> {', '.join(m['firm_attendees'])}", BODY))
            story.append(Spacer(1, 6))
        story.append(Paragraph(FOOTER, SMALL))
    doc(path).build(story)


def render_tour(path, ev):
    story = header([ev["conference_name"], f"Hosted by {ev['broker']}",
                    f"Departing from {ev['hotel']}, {ev['city']}", ev["dates_line"],
                    f"Prepared for: {ev['schedule_for']}"])
    for i, m in enumerate(ev["meetings"], start=1):
        story.append(Paragraph(f"<b>Stop {i} — {m['company']} ({m['ticker']})</b>", ST["Heading4"]))
        for line in (f"{h12(m['start'])} to {h12(m['end'])} · {TYPE[m['format']]}", f"Where: {m['room']}",
                     f"Hosts: {'; '.join(m['company_attendees'])}",
                     f"Travelling: {', '.join(m['firm_attendees'])}"):
            story.append(Paragraph(line, BODY))
        story.append(Spacer(1, 6))
    story.append(Paragraph(FOOTER, SMALL))
    doc(path).build(story)


def events():
    evs = {}

    rng = random.Random(1)
    consumer = [("Maple and Pine Outfitters", "MPOF"), ("Lantern Grocers", "LTGR"), ("Coastline Apparel", "CSTA"),
                ("Bramble Home Goods", "BRHG"), ("Saffron Kitchens", "SAFK"), ("Velvet Leaf Beauty", "VLBT"),
                ("Driftwood Footwear", "DRFW"), ("Copper Kettle Brands", "CPKB"), ("Harbor Lane Retail", "HBLR"),
                ("Silverline Luxury", "SLVL"), ("Meadowgate Foods", "MDGF"), ("Nimble Pet Co", "NMPC"),
                ("Oakridge Outdoors", "OKRO"), ("Sunbeam Beverages", "SNBV")]
    slots = [("08:00", 45), ("09:00", 45), ("10:00", 45), ("11:00", 45), ("12:00", 75), ("13:30", 45), ("14:30", 45)]
    m = schedule(rng, consumer, ["2026-11-16", "2026-11-17"], ["Avery Kim", "Jordan Lee", "Morgan Diaz",
                 "Taylor Brooks"], ["Salon A", "Salon B", "Suite 1802", "Harbor Room"], slots, meal_slot="12:00")
    m[9]["firm_attendees"] = ["Chris Wong"]  # someone not on the roster
    m[3]["room"] = "TBD"
    evs["01_consumer_retail_boston"] = dict(
        layout="grid", conference_name="Consumer & Retail Conference 2026", broker="Example Securities",
        hotel="The Beacon Harbor Hotel", city="Boston, MA", timezone="America/New_York",
        schedule_for="Sample Capital", dates_line="November 16–17, 2026", meetings=m)

    rng = random.Random(2)
    energy = [("Prairie Wind Power", "PRWP"), ("Bluewater Midstream", "BLWM"), ("Granite Ridge Oil", "GRRO"),
              ("Helios Grid", "HLGR"), ("Cobalt Basin Energy", "CBBE"), ("Northern Lights Utilities", "NLUT"),
              ("Redrock Refining", "RDRF"), ("Tidal Storage Systems", "TDSS"), ("Ember Hydrogen", "EMBH"),
              ("Silver Creek Gas", "SCGS")]
    slots = [("08:30", 45), ("09:30", 45), ("10:30", 45), ("12:00", 90), ("14:00", 45)]
    m = schedule(rng, energy, ["2026-12-08", "2026-12-09"], ["Riley Chen", "Daniel Okafor", "Morgan Diaz"],
                 ["Suite 2104", "Bayou Ballroom", "Suite 1410"], slots, meal_slot="12:00", pages={0: 1, 1: 2})
    evs["02_energy_transition_houston"] = dict(
        layout="sections", conference_name="Energy Transition Summit 2026", broker="Northbridge Capital",
        hotel="The Gulfstream Grand", city="Houston, TX", timezone="America/Chicago",
        schedule_for="Sample Capital", dates_line="December 8–9, 2026", meetings=m)

    rng = random.Random(3)
    asia = [("Jade Circuit Semiconductor", "JDCS"), ("Lotus Cloud Systems", "LTCS"),
            ("Harbour Data Centres", "HBDC"), ("Pearl Payments", "PRLP"), ("Monsoon Robotics", "MNRB"),
            ("Bamboo Logistics Tech", "BMLT"), ("Red Lantern Gaming", "RLGM"), ("Skyline Telecom Asia", "SKTA")]
    m = []
    for i, (name, ticker) in enumerate(asia):
        day = "2026-11-24" if i < 4 else "2026-11-25"
        start = ["09:00", "10:30", "13:00", "15:30"][i % 4]
        fmt = "meal" if start == "13:00" else rng.choice(["one_on_one", "group"])
        m.append(mt(day, start, None, fmt, rng.choice(["Orchid Room", "Suite 3301", "Marina Hall"]), name, ticker,
                    execs(rng, rng.choice([1, 2])), [], 1))
    evs["03_asia_tech_singapore"] = dict(
        layout="itinerary", conference_name="Asia Technology Forum 2026", broker="Demo Bank",
        hotel="The Marina Pearl Hotel", city="Singapore", timezone="Asia/Singapore", schedule_for="Priya Shah",
        dates_line="24–25 November 2026", meetings=m)

    rng = random.Random(4)
    fins = [("Thames Mutual Bank", "TMBK"), ("Kingsway Insurance", "KGIN"), ("Albion Asset Managers", "ALAM"),
            ("Fleet Street Payments", "FSPY"), ("Greenwich Re", "GRRE"), ("Mayfair Wealth", "MYFW"),
            ("Cheapside Exchange Group", "CHEX"), ("Highbury Building Society", "HBBS"),
            ("Lombard Lane Capital", "LBLC"), ("Southbank Fintech", "SBFT"), ("Regent Card Services", "RGCS"),
            ("Wharfside Insurers", "WHFI")]
    slots = [("08:30", 40), ("09:20", 40), ("10:10", 40), ("11:00", 40), ("12:15", 60), ("14:00", 40)]
    m = schedule(rng, fins, ["2026-12-01", "2026-12-02"], ["Sam Patel", "Jordan Lee", "Priya Shah"],
                 ["Room 4", "Room 6", "The Library", "Room 2"], slots, meal_slot="12:15")
    m[5]["firm_attendees"] = m[5]["firm_attendees"] + ["Elena Park"]  # not on the roster
    evs["04_financials_london"] = dict(
        layout="list", conference_name="European Financials Conference 2026", broker="Harborline Partners",
        hotel="The Kensington Arms", city="London", timezone="Europe/London", schedule_for="Sample Capital",
        dates_line="1–2 December 2026", meetings=m)

    rng = random.Random(5)
    pre = ["Aster", "Brightwell", "Cedar", "Delta", "Evergreen", "Fulcrum", "Genome", "Halo", "Iris", "Juniper",
           "Kestrel", "Lumina", "Meridian", "Nova", "Orchid", "Pinnacle", "Quill", "Radiant", "Sable", "Terra",
           "Umbra", "Vireo", "Willow", "Xylo", "Yarrow", "Zenith", "Arbor", "Beacon", "Cobalt", "Dawn", "Ember",
           "Fable"]
    suf = ["Therapeutics", "Biosciences", "Medical", "Diagnostics", "Genomics", "Health"]
    hc = [(f"{p} {rng.choice(suf)}", (p[:3] + rng.choice("BDGHMRTX")).upper()) for p in pre]
    slots = [("08:00", 40), ("08:45", 40), ("09:30", 40), ("10:15", 40), ("11:00", 40), ("13:00", 40),
             ("13:45", 40), ("14:30", 40), ("15:15", 40), ("16:00", 40), ("16:45", 40)]
    m = schedule(rng, hc, ["2027-01-12", "2027-01-13", "2027-01-14"], [r["name"] for r in ROSTER],
                 ["Grand Ballroom A", "Grand Ballroom B", "Suite 2201", "Suite 2205", "Nob Hill Room"], slots)
    m[4]["start"], m[4]["end"] = m[3]["start"], plus(m[3]["start"], 40)  # double booking on day one
    m[4]["firm_attendees"] = list(m[3]["firm_attendees"][:1])
    m.append(copy.deepcopy(m[7]))  # the broker printed one meeting twice
    evs["05_healthcare_san_francisco"] = dict(
        layout="grid", conference_name="Healthcare Investor Days 2027", broker="Summit Street Securities",
        hotel="The Embarcadero Plaza Hotel", city="San Francisco, CA", timezone="America/Los_Angeles",
        schedule_for="Sample Capital", dates_line="January 12–14, 2027", meetings=m)

    rng = random.Random(6)
    sites = [("Midwest Rail Works", "MWRW", "Plant tour — 4400 W Fulton St, Chicago"),
             ("Lakeshore Machinery", "LKMC", "HQ — 900 N Lake Shore Dr, Chicago"),
             ("Prairie Steel Fabricators", "PRSF", "Mill — Gary, IN"),
             ("Windy City Aerospace", "WCAS", "Hangar 7, Midway Airport"),
             ("Great Lakes Logistics", "GLLG", "Distribution centre — Joliet, IL"),
             ("Ironbridge Pumps", "IRBP", "Research lab — Schaumburg, IL")]
    starts = ["08:30", "10:15", "11:45", "13:45", "15:15", "16:45"]
    m = [mt("2026-11-19", s, plus(s, 75), "other", where, name, ticker, execs(rng, 2),
            printed(rng, ["Taylor Brooks", "Avery Kim"]), 1)
         for i, ((name, ticker, where), s) in enumerate(zip(sites, starts))]
    evs["06_industrials_field_trip_chicago"] = dict(
        layout="tour", conference_name="Midwest Industrials Field Trip 2026", broker="Pinecrest Securities",
        hotel="The Loop Meridian Hotel", city="Chicago, IL", timezone="America/Chicago",
        schedule_for="Sample Capital", dates_line="Thursday, November 19, 2026", meetings=m)

    rng = random.Random(7)
    japan = [("Sakura Precision", "SKRP"), ("Fujiyama Robotics", "FJRB"), ("Kanto Rail Systems", "KNRS"),
             ("Hoshi Electronics", "HSEL"), ("Minato Trading", "MNTR"), ("Aoba Pharma", "AOBP"),
             ("Kaze Motors", "KZMT"), ("Tsuki Semiconductor", "TSKS"), ("Ume Foods", "UMEF"),
             ("Shinkai Shipping", "SNKS"), ("Kumo Software", "KMSW"), ("Hikari Materials", "HKMT")]
    slots = [("09:00", 50), ("10:00", 50), ("11:00", 50), ("13:30", 50)]
    m = schedule(rng, japan, ["2026-12-14", "2026-12-15", "2026-12-16"], ["Sam Patel", "Daniel Okafor",
                 "Riley Chen"], ["Room Fuji", "Room Sakura", "Suite 4012"], slots)
    evs["07_japan_access_tokyo"] = dict(
        layout="grid24", conference_name="Japan Corporate Access Week 2026", broker="Bayview Markets",
        hotel="The Akasaka Garden Hotel", city="Tokyo", timezone="Asia/Tokyo", schedule_for="Sample Capital",
        dates_line="December 14–16, 2026", meetings=m)

    v2 = copy.deepcopy(evs["01_consumer_retail_boston"])
    rows = v2["meetings"]
    rows[1].update(start="15:30", end="16:15")                               # moved
    rows[3]["room"] = "Suite 1906"                                           # TBD -> room
    rows[5]["firm_attendees"] = rows[5]["firm_attendees"] + ["Taylor Brooks"]  # colleague added
    dropped = rows.pop(10)                                                   # company cancelled
    rows.append(mt("2026-11-17", "15:30", "16:15", "one_on_one", "Salon B", "Juniper Cycles", "JNCY",
                   ["Rosa Varga, CFO"], ["Avery Kim"], 2))                    # new meeting
    rows.sort(key=lambda r: (r["date"], r["start"]))
    v2["note"] = f"Revised November 9, 2026 — {dropped['company']} has withdrawn"
    evs["08_consumer_retail_boston_REVISED"] = v2
    return evs


RENDER = {"grid": render_grid, "sections": render_sections, "itinerary": render_itinerary, "list": render_list,
          "tour": render_tour, "grid24": lambda p, e: render_grid(p, e, h24=True)}


def main(out: Path = OUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, ev in events().items():
        RENDER[ev["layout"]](out / f"{name}.pdf", ev)
        expected = {k: ev[k] for k in ("conference_name", "broker", "hotel", "city", "timezone", "schedule_for")}
        (out / f"{name}.expected.json").write_text(
            json.dumps({**expected, "meetings": ev["meetings"]}, indent=2, ensure_ascii=False) + "\n")
    (out / "roster.demo.json").write_text(json.dumps(ROSTER, indent=2) + "\n")
    print(f"wrote demo pack to {out}")


if __name__ == "__main__":
    main()
