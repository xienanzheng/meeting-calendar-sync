# Meeting Calendar Sync: architecture proposal (2 slides)

Content brief for the two-slide PDF. Theme: Woodline navy `#182958`, cream `#f9f7ed`, beige
`#e3deb0`; Figtree for headings, Manrope for text. For internal use only.

---

## Slide 1: What runs today (prototype)

**Title:** From broker PDF to colleagues' calendars, verified by the coordinator

**Flow, left to right:**
1. **Coordinator (CR)** uploads a broker conference PDF in the browser.
2. **Web app** (React UI + FastAPI, packaged as one Docker image):
   - Claude reads the PDF and returns structured meetings: date, time, room, company and ticker,
     executives, colleagues, PDF page.
   - Roster matching handles initials, aliases and typos. Flags catch missing times, unmatched
     names, double bookings and duplicates.
   - The "By colleague" review shows each meeting next to its highlighted row in the PDF.
   - **Verify = send:** the meeting goes onto the right colleagues' calendars in the same step.
   - **Revised PDFs** are recognised automatically. Only the changes are shown ("Revision 2 — 5
     changes"); CR accepts them and the calendars update.
3. **Claude (swappable):** the Anthropic API (key in the macOS Keychain), Claude Code on the Mac,
   or Microsoft Foundry. One setting switches between them.
4. **Calendars (swappable):** `.ics` files that CR imports today; Microsoft Graph (already built)
   once IT approves it.
5. **Data:** SQLite plus the uploaded PDFs.

**Where it runs:**
- **Locally** on the Mac at 127.0.0.1.
- **Hosted demo** on Cloudflare Containers behind a password-gated Worker. Data there resets
  when the container sleeps; use sample data only.

**Proof points:**
- 285 backend and 49 frontend tests.
- Real Claude extraction scored 100% on the 4 sample schedules (38 meetings), 5–10 s per PDF.

---

## Slide 2: Target on Woodline's Microsoft stack

**Title:** Same app, inside Woodline's Microsoft 365 and Azure

**Components:**
- **Sign-in:** Microsoft Entra ID single sign-on. It's the same account CR already uses for
  Outlook, SharePoint and Teams, so there's no new password. App access is limited to an Entra
  security group ("Calendar coordinators").
- **Front door:** a link or tile on the team's **SharePoint** site, or a Teams tab. Optionally, a
  SharePoint **"Broker schedules" document library** as the drop zone: a new PDF there triggers
  extraction automatically, and a revised PDF is detected as an update.
- **Azure resource group** (e.g. `rg-meeting-calendar-sync-prod`):
  - **App Service / Container Apps** runs the same container image.
  - **Azure SQL Database** replaces SQLite. The code already uses SQLAlchemy, so this is a
    connection-string change.
  - **Blob Storage** holds broker PDFs, private and encrypted.
  - **Key Vault + managed identity** hold all secrets, so no keys exist in config.
  - **Application Insights** provides logs and alerts.
  - Private networking / VNet integration if IT requires it.
- **AI:** Claude through **Microsoft Foundry** (`MCS_EXTRACTOR=foundry`, already built), in
  Woodline's Azure tenant, so PDFs never leave Microsoft's cloud.
- **Calendars:** **Microsoft Graph**, delegated permission `Calendars.ReadWrite.Shared` (already
  built). It writes straight into each colleague's **Outlook** calendar using CR's existing
  delegate access. Edits update events, removals cancel them, and nobody receives an email.

**Flow:** CR signs in (Entra SSO) → uploads, or drops the PDF in SharePoint → Claude on Foundry
extracts → CR reviews and verifies → Graph writes into colleagues' Outlook calendars → a revised
PDF shows only its changes → CR accepts → Outlook updates.

**What IT needs to approve:**
1. An Entra app registration, with admin consent for `Calendars.ReadWrite.Shared` (delegated).
2. A Claude deployment in Microsoft Foundry.
3. A resource group with App Service or Container Apps, SQL, Storage and Key Vault.
4. Optionally, SharePoint library access (`Sites.Selected`) for the drop zone.

**Migration from the prototype:** switch the settings (`MCS_EXTRACTOR=foundry`,
`MCS_CALENDAR_SINK=graph`, the DB URL), deploy the same image, and sign in once as CR.
