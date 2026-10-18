# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Vite + TypeScript frontend with a FastAPI (Python) backend and SQLite. The user picked this in the init interview on 2026-10-17. It runs locally with a single `mcs serve` command at `http://127.0.0.1:8765`. A hosted copy runs the same Docker image on Cloudflare Containers behind a Worker password gate (the user's choice on 2026-10-18). The code lives in a public GitHub repo on the user's personal account.

## Users

A calendar coordinator at Woodline Partners, an investment firm. That is either the user or the firm's coordinator ("CR"). They look after the calendars of 5–6 associates and analysts, with read/write (delegate) access to each colleague's Outlook calendar. They work at a desk, usually in the days before a conference. Their job: turn a broker's meeting schedule into correct calendar entries for the right colleagues.

## Product Purpose

Brokers and conference organisers send schedule PDFs listing one-on-one, group and meal meetings at a hotel. Each meeting has a time, room, company and ticker, the company's executives, and which firm colleagues attend. Today the coordinator re-types every row into each colleague's calendar.

The workflow:
1. The coordinator uploads the PDF.
2. Claude extracts the meetings.
3. The coordinator reviews, corrects and verifies each meeting.
4. Only verified meetings go to the colleagues' calendars.

Success: a ~30-meeting schedule becomes correct calendar entries in minutes. Nothing is sent unverified, times are right in the hotel's timezone, and re-sending after an edit updates the entry instead of duplicating it.

## Positioning

A human-verified bridge from messy, broker-specific PDF layouts to colleagues' calendars. Claude does the reading; the coordinator keeps the final say on every meeting. Wrong times or missing people are flagged before anything is sent.

## Operating Context

- **Inputs:** broker and conference schedule PDFs. Layouts vary by broker: grids by day, sections by company, per-person itineraries. Times are in the hotel's local timezone, often different from the coordinator's own.
- **Calendar:** Microsoft 365 / Outlook. The coordinator has delegate read/write access to colleagues' calendars.
- **Infra:** heavily restricted. Entra app registration and admin consent may not be available, and Claude may later have to run through Microsoft Foundry.
- **Workflow:** upload → review and verify → send. The verification step is the core of the product.

## Capabilities and Constraints

- PDF extraction with Claude. The provider can be switched:
  - Anthropic API (the default when a key is found);
  - local Claude Code;
  - Microsoft Foundry;
  - an offline fake, for tests.
- Calendar output can also be switched:
  - `.ics` files (work today, no IT approval needed);
  - Microsoft Graph, writing directly into colleagues' calendars via delegate access. This needs an Entra app registration and hasn't been tested against a real tenant.
- A roster maps the names printed in PDFs (initials, aliases, typos) to colleagues' emails.
- Flags block sending or warn the coordinator:
  - **block:** missing timezone, date or time; end before start; no attendee;
  - **warn:** assumed end time, unmatched name, fuzzy match, double booking, duplicate.
- The app never sends email or Teams messages.
- Local mode: binds to 127.0.0.1, one user, no login.
- Hosted mode (Cloudflare Containers): a password-gated Worker sits in front; the API key is a Cloudflare secret. Data is ephemeral (it resets when the container sleeps or is redeployed) and the UI says so. The sample roster is seeded on start. Real broker schedules shouldn't go into the hosted copy until the firm's data rules allow it.
- Secrets live in env vars or the macOS Keychain, never in files.
- Not decided or not in v1:
  - merging a revised broker PDF into an earlier upload;
  - an Outlook add-in;
  - cloud deployment.

## Brand Commitments

- The UI uses the Woodline Partners company theme, matched from the public site woodlinepartners.com (the user chose this source on 2026-10-17).
- The repo is public (the user's choice); its README states it is an unofficial prototype, not an official Woodline product. The hosted copy is never openly accessible: a password gate sits in front, optionally with Cloudflare Access too.
- The product name in the UI is "Meeting Calendar Sync".

## Evidence on Hand

- Synthetic broker PDFs with expected extraction JSON in `samples/` (fictional companies and people), used for tests and demos.
- Real broker schedules will be supplied by the user into `private/samples/`. That folder is git-ignored and never committed; it's used only for local extraction testing.
- No real usage data, testimonials or metrics exist. Don't invent any.

## Product Principles

1. **Nothing reaches a colleague's calendar without the coordinator's verification.**
2. **Show the source.** Every extracted meeting traces back to its PDF page, so checking is fast.
3. **Flag problems; don't hide them.** Missing or uncertain data is visible and blocks sending when it would produce a wrong entry.
4. **Simple to run and to use.** One command, three pages (Conferences, Review, Roster). No setup beyond a key.
5. **Swappable infrastructure.** Extraction and calendar back ends change by config as the firm's IT allows.
