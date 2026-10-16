# Meeting Calendar Sync — design

Date: 2026-10-16 · Status: approved for implementation ("implement it, make it swappable") · Path: architectural

## 1. Purpose

A local prototype for an investment firm's calendar coordinator. The coordinator receives
broker conference schedules as PDFs (one-on-one and group meetings at a hotel, with time,
room, company/ticker, company executives and the firm's attendees). Today they re-type every
row into the Outlook calendars of the 5–6 associates/analysts they manage, using delegate
(read/write) access.

The app turns that into: **upload PDF → Claude extracts meetings → coordinator reviews and
fixes them on a dashboard → confirmed meetings go to each analyst's calendar.**

Success: a ~30-meeting broker PDF becomes correct calendar entries in minutes, with nothing
sent that the coordinator has not confirmed, times correct in the hotel's timezone, and
re-sending after an edit updating the existing entry instead of duplicating it.

### What the user said vs. what is assumed

- Said: Outlook / Microsoft 365; broker PDFs for conferences, usually at a hotel; one
  coordinator for 5–6 analysts; heavy infra restrictions; Claude likely reachable via
  Microsoft Foundry; "make it swappable, for now use whatever resources we have".
- Assumed (rulings, see §12): delegate write directly into each analyst's calendar rather
  than sending invites; single local user; no revised-schedule merge in v1.

## 2. Constraints

- Runs locally on the user's Mac. Binds to `127.0.0.1` only. No multi-user auth.
- All demo/test data is synthetic: fictional companies, fictional analysts with
  `@example.com` emails, fictional brokers and hotels. No real firm names, schedules or
  branding anywhere in the repo or UI. The UI is titled "Meeting Calendar Sync".
- Secrets come from environment variables (optionally a git-ignored `.env`). `.env.example`
  lists names only, never values. Access tokens (Graph) live in process memory only — never
  written to disk, logs, the database, or API responses.
- The app never sends email or Teams messages. `.ics` files are produced for the coordinator
  to deliver; Graph writes events directly.
- Uploaded PDFs, the SQLite DB and generated `.ics` files live under `data/` (git-ignored).

## 3. Architecture

```
Browser (React, Vite, TS)  ──►  FastAPI backend (Python, uv)  ──►  Extractor (swappable)
  Upload · Review · Roster          │                               claude-code | anthropic | foundry | fake
                                    ├──►  SQLite (SQLModel)
                                    └──►  Calendar sink (swappable)
                                           ics | graph
```

Production build: FastAPI serves the built frontend from `frontend/dist`, so one command
(`uv run mcs serve`) runs everything at `http://127.0.0.1:8765`. Development: Vite dev
server proxies `/api` to the backend.

### Repository layout

```
Meeting Calendar Sync/
  backend/
    pyproject.toml            # uv project; package "mcs"; console script "mcs"
    mcs/
      config.py               # Settings (env + optional .env)
      db.py                   # engine/session/init
      models.py               # SQLModel tables
      schemas.py              # Pydantic API request/response models
      extraction/
        __init__.py           # get_extractor(settings) factory, Extractor protocol, ExtractionError
        schema.py             # ExtractionResult models, JSON schema, prompt text
        claude_code.py        # ClaudeCodeExtractor (local `claude -p`)
        anthropic_api.py      # AnthropicExtractor (Anthropic or AnthropicFoundry client)
        fake.py               # FakeExtractor (sample PDFs only)
      roster.py               # name → analyst matching
      normalize.py            # extraction → meetings; time parsing; flags
      calendar/
        __init__.py           # get_sink(settings) factory, CalendarSink protocol
        content.py            # event subject/location/body/UTC times/content hash
        planner.py            # which create/update/cancel actions a send needs
        ics.py                # IcsSink
        graph.py              # GraphSink
        graph_auth.py         # MSAL device-code flow, in-memory token
      api/
        app.py                # create_app(settings); static frontend
        routes_conferences.py
        routes_meetings.py
        routes_roster.py
        routes_sync.py
        routes_system.py      # /api/health, /api/config, Graph login
      cli.py                  # `mcs serve`, `mcs seed-roster`
    scripts/
      make_sample_pdfs.py     # generates samples/*.pdf (reportlab)
      eval_extraction.py      # runs the configured extractor on samples, scores vs expected
    tests/
  frontend/                   # Vite + React + TypeScript + Tailwind
  samples/                    # synthetic broker PDFs, *.expected.json, roster.sample.json (committed)
  data/                       # git-ignored runtime data
  .env.example
  README.md
```

## 4. Data model (SQLite via SQLModel)

**Analyst** (the roster): `id`, `name`, `email` (unique), `aliases` (JSON list of strings,
e.g. `["A. Kim", "Avery K."]`), `active` (bool, default true).

**Conference**: `id`, `name`, `broker`, `hotel`, `city`, `timezone` (IANA name or null),
`schedule_for` (who the PDF is addressed to, as printed), `pdf_filename` (original name),
`pdf_path` (stored path under `data/uploads/`), `extractor` (provider name that produced it),
`created_at`.

**Meeting**: `id`, `conference_id`, `date` (nullable), `start_time` (nullable),
`end_time` (nullable), `end_assumed` (bool), `room`, `company`, `ticker` (nullable),
`format` (`one_on_one` | `group` | `meal` | `other`), `company_attendees` (JSON list),
`raw_attendee_names` (JSON list — firm attendee names exactly as printed),
`ignored_names` (JSON list — raw names the coordinator dismissed), `notes`,
`source_page` (nullable int, 1-based), `status` (`draft` | `confirmed` | `cancelled`),
`created_at`, `updated_at`.

**MeetingAttendee**: `meeting_id`, `analyst_id`, `match` (`exact` | `alias` | `initial` |
`fuzzy` | `manual` | `default`). Primary key (`meeting_id`, `analyst_id`).

**SyncRecord**: `id`, `meeting_id`, `analyst_id`, `sink` (`ics` | `graph`), `external_id`
(ICS UID or Graph event id), `content_hash`, `sequence` (int, starts 0), `state` (`active` |
`cancelled` | `failed`), `last_error` (nullable), `updated_at`. Unique
(`meeting_id`, `analyst_id`, `sink`).

Meeting flags are **computed on read** from current state (§6), never stored.

## 5. Extraction (swappable)

### Interface

```python
class Extractor(Protocol):
    name: str
    def extract(self, pdf_path: Path) -> ExtractionResult: ...

class ExtractionError(Exception): ...   # message is shown to the coordinator
```

`get_extractor(settings)` returns the provider named by `MCS_EXTRACTOR`.

### Result shape (also the JSON schema given to Claude)

`ExtractionResult`: `conference_name`, `broker`, `hotel`, `city`, `timezone` (IANA guess
from the city), `schedule_for`, `meetings: list[ExtractedMeeting]` — all fields optional
except `meetings`.

`ExtractedMeeting`: `date` ("YYYY-MM-DD"), `start` ("HH:MM", 24h, hotel-local), `end`,
`room`, `company` (required), `ticker`, `format` (`one_on_one` | `group` | `meal` |
`other`), `company_attendees` (list), `firm_attendees` (list), `notes`, `page` (1-based).

One prompt and one JSON schema are shared by every provider (`extraction/schema.py`). The
prompt tells Claude to: copy names as printed; never invent values (omit unknown fields);
use 24-hour local times as printed; infer the year from the document header; set `format`
from cues ("1x1"/"one-on-one" → `one_on_one`, "group"/"small group" → `group`,
"lunch"/"breakfast"/"dinner" → `meal`); put the schedule's addressee in `schedule_for`;
list the firm's attendees per row in `firm_attendees`; report the 1-based page.

Provider output is validated with Pydantic. Meeting items that fail validation (e.g. no
company) are skipped and counted (`skipped_items`), not fatal. An empty `meetings` list is
not an error: the conference is created with zero meetings.

### Providers

| `MCS_EXTRACTOR` | How | Needs |
|---|---|---|
| `claude-code` (default) | Subprocess: `claude -p <prompt> --tools Read --allowedTools Read --output-format json --json-schema <schema> --no-session-persistence --model <model> --system-prompt <short prompt>`; stdin from `/dev/null`; cwd = a temp dir holding a copy of the PDF; env stripped of `CLAUDECODE` and every `CLAUDE_CODE_*` variable; reads `structured_output` from the JSON result. | `claude` CLI logged in |
| `anthropic` | `anthropic.Anthropic()`; PDF sent as a base64 `document` block; forced tool use (`tools=[record_meetings]`, `tool_choice={"type":"tool","name":"record_meetings"}`) whose `input_schema` is the shared schema. | `ANTHROPIC_API_KEY` |
| `foundry` | Same code as `anthropic` with `anthropic.AnthropicFoundry(resource=…, api_key=…)`; if no key, Entra auth via `azure.identity.DefaultAzureCredential` + `get_bearer_token_provider(cred, "https://ai.azure.com/.default")` (lazy import; clear error if `azure-identity` missing). | `ANTHROPIC_FOUNDRY_RESOURCE` + key or Entra login |
| `fake` | Returns the committed `samples/<name>.expected.json` for a PDF whose SHA-256 matches a `samples/*.pdf`; any other PDF raises `ExtractionError`. | nothing (tests, offline demo) |

Model: `MCS_MODEL` overrides; defaults are `sonnet` for `claude-code` and `claude-sonnet-5`
for `anthropic`/`foundry`. Timeout `MCS_EXTRACT_TIMEOUT` (default 240 s). Upload limit
20 MB, PDF only (extension `.pdf` and `%PDF` magic bytes).

Extraction runs synchronously inside the upload request; the UI shows a spinner
("Reading the PDF with Claude — usually 30–60 s").

## 6. Normalization, roster matching and flags

### Creating meetings from an extraction (`normalize.py`)

- Times: accept "HH:MM", "H:MM", "8:00 AM", "8am", "8:00am"; unparseable → null.
  Dates: "YYYY-MM-DD" (also tolerate "2026-11-10T…"); unparseable → null.
- Missing end with a start → end = start + `MCS_DEFAULT_MEETING_MINUTES` (default 45),
  `end_assumed = true`.
- Conference timezone: the extraction's `timezone` if it is a valid `zoneinfo` key, else null.
- Firm attendees for a meeting = the row's `firm_attendees`; if the row has none and
  `schedule_for` matches a roster analyst, that analyst; plus any "default attendees" the
  coordinator chose at upload (`match = default`).

### Roster matching (`roster.py`)

`match_name(raw, analysts) -> MatchResult(analyst_id | None, match_kind | None)`.
Normalise both sides (lowercase, strip punctuation and extra spaces). In order:
1. `exact` — equals an analyst's full name.
2. `alias` — equals one of the analyst's aliases.
3. `initial` — patterns "A. Kim" / "A Kim" / "Avery K." / "Avery K" match exactly one
   analyst by first-initial+last-name or first-name+last-initial.
4. `fuzzy` — best `difflib.SequenceMatcher` ratio ≥ 0.85 against full names and aliases,
   and unique (runner-up < best − 0.05).
5. Otherwise no match. Ambiguous matches (two analysts tie at any step) → no match.
Inactive analysts are never matched.

### Flags (computed on read)

`compute_flags(conference, meetings, attendees, analysts) -> dict[meeting_id, list[Flag]]`;
`Flag = {code, severity: "block" | "warn", message}`. Cancelled meetings get no flags and are
excluded from the overlap/duplicate checks.

| code | severity | when |
|---|---|---|
| `no_timezone` | block | conference timezone is null |
| `missing_date` | block | date null |
| `missing_time` | block | start or end null |
| `end_before_start` | block | end ≤ start |
| `no_attendee` | block | no MeetingAttendee rows |
| `assumed_end` | warn | `end_assumed` |
| `unmatched_name` | warn | a raw name not matched to any attendee and not in `ignored_names` |
| `fuzzy_match` | warn | any attendee with `match = fuzzy` |
| `double_booked` | warn | an attendee is in another overlapping non-cancelled meeting (same date) |
| `duplicate` | warn | another non-cancelled meeting with same date, start and company (case-insensitive) |

### Status rules

- Confirming a meeting with any `block` flag is rejected (HTTP 409 with the flags).
- An edit that leaves a confirmed meeting with a `block` flag moves it back to `draft`.
- "Confirm all ready" confirms every draft meeting with no `block` flags.
- Deleting a meeting that has never been sent removes it; deleting one with an active
  SyncRecord sets `status = cancelled` (the next send cancels it in calendars).

## 7. Calendar output (swappable)

### Event content (`calendar/content.py`, shared by both sinks)

- Subject: `"{ticker} – {company} ({label})"`, or `"{company} ({label})"` without a ticker.
  Labels: `one_on_one` → "1x1", `group` → "Group", `meal` → "Meal", `other` → "Meeting".
- Location: `"{hotel} – {room}"`, dropping empty parts.
- Body (plain text, one item per line): conference name; "Company: " executives;
  "Also attending: " the other firm attendees; notes; "Source: {pdf_filename}, page {n}".
- Start/end: hotel-local date+time converted to UTC via the conference timezone.
- `content_hash`: SHA-256 of canonical JSON of subject, location, body, start UTC, end UTC.

### Planning a send (`calendar/planner.py`, pure function)

For one conference and one sink, compare meetings × attendees with existing SyncRecords:

- confirmed meeting, attendee with no record (or a `failed`/`cancelled` record) → `create`
- confirmed meeting, active record, hash differs → `update` (sequence + 1)
- confirmed meeting, active record, same hash → skip
- cancelled meeting, or analyst no longer an attendee, with an active record → `cancel`
- draft meetings are never sent; their existing active records are left alone

The send endpoint returns a preview (`dry_run=true`) or executes. Results are per
(meeting, analyst): `ok` or the error text. SyncRecords are written per item, so a partial
failure keeps the successes and a re-send retries only what failed or changed.

### Sinks

```python
class CalendarSink(Protocol):
    name: str                       # "ics" | "graph"
    def apply(self, conference, actions: list[SyncAction]) -> list[SyncOutcome]: ...
```

**`ics` (default).** For every analyst touched, (re)writes
`data/ics/conference-{id}/{analyst-slug}.ics` containing all of that analyst's events in the
conference (`METHOD:PUBLISH`; active → `STATUS:CONFIRMED`, cancelled →
`STATUS:CANCELLED`), with `UID: mcs-{meeting_id}-{analyst_id}@meeting-calendar-sync`,
`SEQUENCE`, `DTSTAMP`, and UTC `DTSTART`/`DTEND` (no VTIMEZONE needed). Built with the
`icalendar` package. `external_id` = UID. Downloads: one file per analyst and a zip of all.

**`graph`.** Delegated Microsoft Graph, writing straight into each analyst's calendar via
the coordinator's delegate access:
- create `POST /v1.0/users/{email}/calendar/events` with `transactionId =
  "mcs-{meeting_id}-{analyst_id}-{sequence}"`; update `PATCH /v1.0/users/{email}/events/{id}`;
  cancel `DELETE /v1.0/users/{email}/events/{id}` (404 counts as done).
- body: subject, `body {contentType: "text"}`, `start`/`end` as `{dateTime, timeZone: "UTC"}`,
  `location.displayName`, `showAs: "busy"`.
- errors per item: 401 → "Sign in to Microsoft again"; 403 → "No delegate access to
  {email}'s calendar"; 429 → wait `Retry-After` (cap 10 s) and retry once; others → status +
  Graph error message.
- `GraphSink(token_provider: Callable[[], str], client: httpx.Client)` — both injectable.
- Auth (`graph_auth.py`): MSAL `PublicClientApplication(client_id=MCS_GRAPH_CLIENT_ID,
  authority="https://login.microsoftonline.com/{MCS_GRAPH_TENANT_ID}")`, device-code flow,
  scope `Calendars.ReadWrite.Shared`, in-memory token cache only. The UI starts sign-in and
  shows the code and URL.
- Tested only against a mocked transport. Not yet tested against a real tenant — stated in
  the README.

`MCS_CALENDAR_SINK` picks the sink (default `ics`); SyncRecords are kept per sink.

## 8. HTTP API

| Method & path | Purpose |
|---|---|
| `GET /api/health` | `{ok: true}` |
| `GET /api/config` | active extractor, model, sink, Graph configured/signed-in (no secrets) |
| `POST /api/conferences` | multipart `file` + optional `default_attendee_ids` (comma list); extracts; returns the conference detail + `skipped_items` |
| `GET /api/conferences` | list with meeting counts |
| `GET /api/conferences/{id}` | conference + meetings (with attendees, flags, sync status) |
| `PATCH /api/conferences/{id}` | name, broker, hotel, city, timezone (validated IANA) |
| `DELETE /api/conferences/{id}` | delete conference, meetings and local files (does not touch calendars) |
| `GET /api/conferences/{id}/pdf` | the uploaded PDF (inline) |
| `POST /api/conferences/{id}/meetings` | add a manual meeting |
| `PATCH /api/meetings/{id}` | edit fields, `attendee_ids` (sets `match = manual` for new ones), `ignored_names` |
| `POST /api/meetings/{id}/confirm` · `POST /api/meetings/{id}/unconfirm` | status changes (§6) |
| `POST /api/conferences/{id}/confirm-ready` | confirm all ready drafts |
| `DELETE /api/meetings/{id}` | delete or cancel (§6) |
| `POST /api/conferences/{id}/send?dry_run=true\|false` | plan / execute with the active sink |
| `GET /api/conferences/{id}/ics/{analyst_id}` · `GET /api/conferences/{id}/ics.zip` | ics downloads |
| `GET/POST /api/roster` · `PATCH/DELETE /api/roster/{id}` | roster CRUD |
| `POST /api/graph/login` · `GET /api/graph/status` | start device-code sign-in / poll |

Meeting payloads carry a `sync` summary per attendee: `not_sent` | `sent` | `changed`
(confirmed, active record, hash differs) | `failed` (with error) | `cancelled`.

Errors: extraction failure → 502 `{detail}`; bad upload → 400; not found → 404; status
conflict → 409. All error bodies are JSON `{detail}`.

## 9. Frontend

Vite + React + TypeScript + Tailwind. A small typed API client (`src/api.ts`). Pages:

1. **Conferences** (`/`): upload card (drag-and-drop or picker; optional "default attendees"
   multi-select from the roster; Extract button with spinner and error display) and the list
   of conferences (name, hotel, dates, meeting counts by status). Header shows the active
   extractor and calendar sink as badges.
2. **Review** (`/conferences/:id`):
   - Header: editable conference name, hotel, city; timezone picker (IANA list from
     `Intl.supportedValuesOf('timeZone')`); counts (meetings, blocked, warnings, confirmed,
     sent/changed).
   - Meetings grouped by date, sorted by start. Each row: confirm checkbox; start–end
     (editable; when the coordinator's browser timezone differs from the hotel's, a muted hint
     shows their local time, e.g. "5:00 AM your time"); company + ticker; room; format;
     attendee chips (add/remove from roster); unmatched raw names with "dismiss"; flag chips
     (red = block, amber = warn, message on hover); sync status; actions (view source page,
     delete/cancel).
   - Inline edits save on blur/enter via PATCH and refresh flags.
   - "Add meeting", "Confirm all ready".
   - Source panel: the PDF in an `<iframe src="/api/conferences/{id}/pdf#page={n}">`,
     toggled per row.
   - "Send to calendars": opens a preview (dry run) grouped by analyst with
     create/update/cancel counts → Confirm → results per item; for `ics`, download links per
     analyst and "Download all (.zip)"; for `graph`, a sign-in prompt if not signed in.
3. **Roster** (`/roster`): table of analysts (name, email, aliases, active) with add, edit,
   delete.

## 10. Error handling summary

- Extraction: CLI missing / not logged in / timeout / invalid JSON / API errors →
  `ExtractionError` with a human-readable message → 502 → shown on the upload card with
  "Try again". The uploaded PDF is kept only if extraction succeeds.
- Invalid timezone in PATCH → 400 listing the problem.
- Send: per-item outcomes; a failed item never blocks others; failures show on the row.
- Graph not configured (no client/tenant id) and sink = graph → send returns 400 "Graph is
  not configured"; not signed in → 401 with a prompt to sign in.

## 11. Testing

- Backend `pytest` (no network, no real Claude):
  - roster matching cases (each match kind, ambiguity, inactive, unmatched);
  - time/date parsing and assumed end; every flag code; status rules;
  - planner (create/update/skip/cancel/draft-ignored/failed-retried);
  - content (subject/location/body/UTC conversion across DST; hash stability);
  - ics (parse the output back with `icalendar`; UIDs, SEQUENCE, CANCELLED);
  - graph (`httpx.MockTransport`: create/update/cancel, 401/403/404/429 handling, no token in
    errors);
  - extractors: claude-code via an injected runner (and a fake `claude` script for the
    subprocess wiring: env stripping, flags, timeout, error JSON); anthropic/foundry via a
    fake client asserting the request shape (document block, forced tool); fake extractor
    hashing; factory selection;
  - API end-to-end with `TestClient`, a temp data dir and the fake extractor: upload sample →
    review payload → edit → confirm → send dry run → send (ics) → download → edit → re-send
    produces an update with SEQUENCE+1 → delete sent meeting → re-send cancels.
- Frontend: `vitest` for pure helpers (grouping/sorting, time formatting incl. local-time hint,
  flag summaries); `npm run build` (type-check) must pass.
- `scripts/eval_extraction.py`: runs the configured extractor on each sample PDF and prints
  field-level accuracy against `*.expected.json`. Run manually (uses Claude), not in pytest.
- Final manual smoke in a browser with the real `claude-code` extractor.

### Sample data (`samples/`, synthetic, committed)

`scripts/make_sample_pdfs.py` (reportlab) generates three layouts with fictional companies
(clearly fictional names; a footer "Sample data — fictional companies and people"):
1. `broker_a_grid.pdf` — two-day conference in New York (`America/New_York`); one table per
   day: Time | Room | Company (Ticker) | Management | Attendees; ~12 meetings incl. a group
   lunch and a room "TBD".
2. `broker_b_by_company.pdf` — two-page summit in Las Vegas (`America/Los_Angeles`); sections
   per company with "Format / Time (10:30am-11:15am) / Location / Attendees" lines; initials
   ("A. Kim"); ~8 meetings incl. one double-booking.
3. `broker_c_itinerary.pdf` — London (`Europe/London`) itinerary "Itinerary for: Sam Patel";
   start times only (no ends); ~6 meetings.

`samples/roster.sample.json`: six fictional analysts (Avery Kim, Sam Patel, Jordan Lee,
Riley Chen, Morgan Diaz, Taylor Brooks; `@example.com`) with a few aliases. The PDFs also
contain one name not on the roster ("Chris Wong") to exercise `unmatched_name`.

## 12. Rulings made without asking

- **Direct write, not invites.** Graph writes into each analyst's calendar (delegate access),
  one event per analyst per meeting; no invite emails. Matches the coordinator's current
  practice. Cost if wrong: switch `graph.py` to a single organizer event with attendees.
- **UTC on the wire.** Both sinks send UTC times; Outlook renders local time. Avoids
  Windows/IANA timezone-name mapping.
- **Unmatched names warn, never block.** Group meetings can list other firms' people.
- **No revised-PDF merge in v1.** A revised broker PDF is uploaded as a new conference;
  editing within a conference and re-sending is idempotent. Merge/diff is the first follow-up.
- **Synchronous extraction.** One request, 30–60 s, spinner. Fine for one local user.
- **Forced tool use for API providers** rather than a structured-output parameter: works
  identically on Anthropic and Foundry.

## 13. Out of scope (v1)

Revised-schedule merge; Outlook add-in; Power Automate; sending emails/invites; multi-user
auth; cloud deployment; Teams; recurring events; attachments.
