---
version: 1
slug: "frontend-src-pages-reviewpage-tsx"
primary_target: "frontend/src/pages/ReviewPage.tsx"
related_targets: ["frontend/src/App.tsx"]
---

# Review surface — conference review ("By colleague")

Scope: the Review page (`/conferences/:id`) plus the shell it shares with Conferences and Roster. Mode: Operate.

Audience and job: Woodline's calendar coordinator verifies a broker conference schedule (often 60+ meetings over 2–3 days) before it reaches 5–6 colleagues' Outlook calendars. Used on a laptop and on an external monitor. Must not look like a marketing site: no photos, no hero banners.

Content: the extracted meetings (time in hotel timezone with the viewer's local time hint, company and ticker, executives, format, room, colleagues, flags), the source PDF page, and sync state per colleague.

Unresolved: none for v1. A keyboard shortcut layer (J/K to move, V to verify) is a stretch goal, not a requirement.

## Direction contract

THESIS: Verify the schedule the way each colleague will live it — one itinerary per person, exactly what lands in their calendar. Refuses the category default: one undifferentiated spreadsheet of every row.

OWN-WORLD: Woodline navy #182958 shell bar and selection; cream #f9f7ed ground; cream #f2efdb colleague rail; beige #e3deb0 primary action on navy; mid blue #475b90 for tickers and day labels. Figtree for headings and numbers, Manrope for UI text, Libre Baskerville only in the WOODLINE wordmark. White tables with beige hairline rules. States are small tilted stamps: VERIFIED navy, SENT ✓ green #48a942, NEEDS … red #d33141, DRAFT muted and flat.

STORY: The coordinator reads the conference totals, picks a colleague (or All), checks each meeting against the highlighted PDF row and verifies it in one click; verifying puts it straight onto the right colleagues' calendars (shared meetings update everyone). When the broker sends a revised PDF she reviews only what changed, accepts, and calendars follow, always knowing what is draft, verified or on calendars.

FIRST VIEWPORT: 64px navy top bar: mark plus wordmark, product name, conference with hotel and timezone, totals, the calendar sync status ("On calendars ✓" / "2 failed — Retry" / "Sign in to Microsoft") and a beige "Verify all ready (N)" button; when a revised PDF is pending, a cream-2 strip under the bar reads "Revision N — K changes" with Review / Accept all / Discard. A 250px colleague rail: All, six colleagues with counts and flag dots, then Not on roster. Main column: the colleague's name, status filter chips, and a day-grouped timetable (Time with local hint | Company + ticker + executives · format | Room | Shared with | Status stamp). A 400px source panel: the PDF page, editable fields, the flag note, and "Verify meeting".

FORM: "By colleague", position 6 of 7 on the ordered list; seed key 3405b9f3. Signature move: the timetable column rhythm (columns never move, rows rank by time) with self-stamping states (verify stamps, send ticks, cancel strikes; nothing disappears). Raised from the split-flap board and the airline ticket wallet.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
