# Personal Google Calendar demo

Use **YOUR_GOOGLE_ACCOUNT@gmail.com** as the live calendar fallback. Double-click **Start Google Demo.command** and open **http://127.0.0.1:8767**.

The demo keeps the PDF extraction and review flow. Verify creates entries in **Meeting Calendar Sync Demo**. Editing a verified meeting or accepting a revised PDF updates those entries. Cancelling a meeting removes them. Each sample colleague has a `[Demo · Name]` entry in the same secondary calendar, with no email attendees or invitations.

## Connect Google, once

This Mac already has a Google Calendar OAuth registration named **Calendar_Agent** from the user's calendar CLI setup. Its client configuration is kept in `private/google-demo-client.json`; it is ignored by Git. The old calendar CLI refresh tokens have expired, so the demo requests a fresh interactive grant and keeps its own credentials separately.

From this project's `backend` directory:

```sh
uv run mcs google-login --account YOUR_GOOGLE_ACCOUNT@gmail.com --client-file ../private/google-demo-client.json
```

Open the Google authorization URL printed by the command, sign in, and review Google's calendar permission request. The command checks that Google identifies the selected primary calendar as **YOUR_GOOGLE_ACCOUNT@gmail.com** before saving credentials. The loopback callback is local to this Mac.

The Google library refreshes authorization when possible. If Google revokes or expires the grant, run the login command again. Credentials are saved with owner-only permissions under the ignored `data/google-demo/<account>/google-oauth.json` path. They are never included in API responses or committed. On another machine, supply a standard Google Desktop OAuth client JSON from a project you control; the private client file is intentionally not shipped.

## Walkthrough

1. Upload `samples/broker_a_grid.pdf` and review **Cobalt Freight Lines**.
2. Verify that meeting. In [Google Calendar](https://calendar.google.com), enable **Meeting Calendar Sync Demo** and view **November 10, 2026**. Cobalt starts at **10:00 New York / 07:00 Pacific**, with one entry for Avery and one for Riley.
3. Change its room and save. The existing entries update.
4. Upload `samples/broker_a_grid_v2.pdf` and accept the Cobalt time change. Those same entries move to **14:30 New York / 11:30 Pacific**. Retry does not add duplicates.
5. Cancel the meeting to remove its entries.

The Google demo has a separate account-specific database from Outlook and ICS. Its target binding is stored alongside the database in `google-demo-target.json`. The app checks the signed-in account and the calendar's ownership before every sync, rejects primary/shared calendars, and stops on duplicate demo calendar names or a missing bound calendar. Keep the database and binding together when resetting a live demo.

## Current verification

The automated tests cover account mismatch, secondary-calendar selection, no-invitation payloads, stable IDs after a lost response, updates, cancellation, API configuration, and the launcher. Live create/update/read-back is pending completion of the current Google authorization.

The Outlook version remains at port 8766. Microsoft sign-in succeeded, but that personal account has no Azure directory and the portal does not allow it to register a new application. It needs a directory before the Graph integration can be connected.

References: [Google's installed-app quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python), [create a secondary calendar](https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert), and [create events with client-supplied IDs](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert).
