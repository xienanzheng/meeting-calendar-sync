# Demo pack: 8 mock broker schedules

Every broker, hotel, company and person here is fictional. Regenerate the pack with
`cd backend && uv run python scripts/make_demo_pdfs.py`.

**Colleagues** (`roster.demo.json`): Avery Kim, Sam Patel, Jordan Lee, Riley Chen, Morgan Diaz,
Taylor Brooks, Priya Shah, Daniel Okafor.

| # | PDF | Broker · event | Where (timezone) | Layout | What it shows |
|---|---|---|---|---|---|
| 1 | `01_consumer_retail_boston.pdf` | Example Securities · Consumer & Retail Conference | Boston (ET) | Grid by day | 14 meetings. "A. Kim" initials match. One row has only **Chris Wong**, who isn't on the roster, so it shows NEEDS COLLEAGUE. One room is **TBD**. |
| 2 | `02_energy_transition_houston.pdf` | Northbridge Capital · Energy Transition Summit | Houston (CT) | One section per company, `10:30am-11:15am` | **Rilay Chen** fuzzy-matches Riley Chen. **D. Okafor** and **Morgan D.** match by initial. A lunch is recognised as a meal. |
| 3 | `03_asia_tech_singapore.pdf` | Demo Bank · Asia Technology Forum | Singapore (SGT) | Itinerary for **Priya Shah**, 24h start times only | Every meeting goes to Priya. End times are assumed (+45 min). Your local-time hint is a big shift (e.g. "5:00 PM PT, day before"). |
| 4 | `04_financials_london.pdf` | Harborline Partners · European Financials | London (UK) | Running list, `08:30–09:10 · Room 4 · 1x1 — …` | Matches the alias **Samir Patel** and **Priya S.**; **Elena Park** isn't on the roster. |
| 5 | `05_healthcare_san_francisco.pdf` | Summit Street Securities · Healthcare Investor Days | San Francisco (PT) | Grid, 3 days | The **volume test: 33 meetings**, every colleague. It includes a **double booking** and a **duplicate row** printed twice by the broker. |
| 6 | `06_industrials_field_trip_chicago.pdf` | Pinecrest Securities · Midwest Industrials Field Trip | Chicago (CT) | Bus-tour stops ("Stop 1 — …", "Where: Plant tour …") | A different event type: site visits at company sites, with **Tay Brooks** as an alias. |
| 7 | `07_japan_access_tokyo.pdf` | Bayview Markets · Japan Corporate Access Week | Tokyo (JST) | Grid with 24h times, 3 days | A far timezone (the hint shows the day before, in your time). |
| 8 | `08_consumer_retail_boston_REVISED.pdf` | Same broker as #1, revised Nov 9 | Boston (ET) | Grid | **Upload after #1** to show it's detected as **Revision 2**, with the changes listed below. |

PDF #8 contains these changes:
- a meeting moved to 3:30 PM;
- the TBD room is now Suite 1906;
- Taylor Brooks has been added to a meeting;
- one company has withdrawn;
- Juniper Cycles is new.

## Suggested 5-minute demo
1. **Roster:** open Roster and show the eight colleagues and their aliases.
2. **Upload #1** (Boston). Claude reads it in about 10 s.
   1. Open **Avery Kim**: her itinerary, the times, and the source PDF with the row highlighted.
   2. Under *Not on roster*, click **Chris Wong** and assign the meeting to Jordan Lee. Click Dismiss, and the flag clears.
   3. Fix the TBD room, then **Verify all ready**. The status shows "N on calendars". Open *Calendar files* to show the `.ics` files CR would import.
3. **Upload #8** (the revised Boston PDF). It's detected as **Revision 2 — 5 changes**. Show the before → after list and click **Accept all**. The moved meeting and the room update on the colleagues' calendars, the withdrawn company is removed, and the new one is added.
4. **Upload #5** (San Francisco, 33 meetings). Use the **Warnings** chip to find the double booking and the duplicate. This is the scale story.
5. **Upload #3 or #7.** Show the itinerary layout and the timezone hints. That's the "different broker formats" story.
6. Optionally, upload #2, #4 or #6 to show more layouts.

Upload PDFs in the order above, so #8 lands as a revision of #1. To upload #8 as its own conference instead, tick "Upload as a new conference instead".
