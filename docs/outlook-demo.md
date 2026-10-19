# Personal Outlook demo

Run the existing review app against **YOUR_OUTLOOK_ACCOUNT@hotmail.com**. The demo uses one secondary calendar called **Meeting Calendar Sync Demo**. The existing delegate integration remains available as `MCS_CALENDAR_SINK=graph` for a work tenant.

## Start

Double-click `Start Outlook Demo.command`, or run from this project:

```sh
cd backend
uv run mcs serve --outlook-demo YOUR_OUTLOOK_ACCOUNT@hotmail.com --graph-client-id YOUR_APPLICATION_CLIENT_ID
```

Open **http://127.0.0.1:8766**. The demo seeds the fictional roster automatically and uses an account-specific database under `data/outlook-demo/`, separate from the regular app. It keeps your configured AI extractor. To make the launcher remember the app registration, add `MCS_GRAPH_CLIENT_ID=YOUR_APPLICATION_CLIENT_ID` to the project's local `.env` file (preserving its other settings).

## Microsoft setup, once

An email address alone cannot authorize Graph. This demo needs its own Microsoft app registration and your interactive consent:

1. Open [Microsoft Entra app registrations](https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade) in a directory where you can register an application. Choose **New registration**, named **Meeting Calendar Sync Personal Demo**.
2. Choose **Personal Microsoft accounts only** (or **Accounts in any organizational directory and personal Microsoft accounts**). No redirect URI is needed for the device-code flow.
3. Under **Authentication**, enable **Allow public client flows**. Under **API permissions**, add Microsoft Graph's **delegated** `Calendars.ReadWrite` permission. This personal demo does not use `Calendars.ReadWrite.Shared` or application permissions.
4. Copy the **Application (client) ID** from Overview. Supply it to the command above or the project's `.env`. A client secret is not required.
5. In a conference's review screen, click **Sign in to Microsoft**. Open Microsoft's device-login page, enter the displayed code, and sign in as **YOUR_OUTLOOK_ACCOUNT@hotmail.com**. Review Microsoft's calendar permission request and complete consent there.

If the portal reports that your account has no directory or cannot register apps, the registration must be created in a directory you administer, or by its administrator, with personal accounts enabled. This is separate from signing into the Hotmail mailbox. Do not reuse another application's client ID.

## Walkthrough

1. Upload `samples/broker_a_grid.pdf`. Review the extraction alongside the PDF, then verify **Cobalt Freight Lines**.
2. Open [Outlook Calendar](https://outlook.live.com/calendar/), enable **Meeting Calendar Sync Demo**, and navigate to **November 10, 2026**. The original Cobalt meeting is **10:00–10:45 America/New_York** (07:00–07:45 Pacific). Outlook displays times in its configured timezone.
3. Each sample colleague gets a separate `[Demo · Name]` entry in your demo calendar, showing how the same meeting would appear in several colleagues' calendars. The app does not add email attendees or send invitations.
4. Upload `samples/broker_a_grid_v2.pdf` and accept the Cobalt time change. The same entries move to **14:30–15:15 New York time**; they retain their Graph event IDs. Editing a verified room also patches the existing entries. Retry has no work after a successful sync.
5. Delete/cancel the meeting in the app to remove its entries from the demo calendar.

The first approved sync creates or reuses the named secondary calendar. Its account, app ID, and calendar ID are stored locally in `outlook-demo-target.json`; tokens remain in memory. Restarting the server requires Microsoft sign-in again. Pending verified entries sync when sign-in finishes.

The app checks the bound calendar before each sync, rejects a default calendar, and stops if the account/app changes, the calendar is missing, or duplicate calendar names make selection ambiguous. Keep the demo database and target binding together; do not delete one independently to reset a demo that still has live entries.

## Verification status

**2026-10-19:** Hotmail sign-in completed. The Azure portal confirmed that this personal account has no directory and cannot create an app registration outside one. Live Outlook sync is therefore blocked on directory/app registration. A separate [Google Calendar fallback](google-demo.md) is available at port 8767.

Automated tests simulate Microsoft's HTTP boundary and exercise calendar selection, account matching, no-invitation payloads, retries, the review API, PDF revisions, updates, and cancellation. A live Hotmail create/update/read-back is **pending Microsoft sign-in and app registration**; automated tests do not establish that the account is connected.

Microsoft references: [create a personal calendar](https://learn.microsoft.com/en-us/graph/api/user-post-calendars?view=graph-rest-1.0), [create an event](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0), and [device-code sign-in](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code).
