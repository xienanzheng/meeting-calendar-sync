---
name: Meeting Calendar Sync
description: Woodline's internal desk for verifying broker conference schedules before they reach colleagues' Outlook calendars.
colors:
  navy: "#182958"
  navy-2: "#283968"
  navy-3: "#101d42"
  blue: "#475b90"
  beige: "#e3deb0"
  beige-2: "#ece8c4"
  beige-3: "#d6d09a"
  cream: "#f9f7ed"
  cream-2: "#f2efdb"
  head: "#fbfaf3"
  select: "#eef0f8"
  skeleton: "#ebe7cf"
  line: "#e6e1c7"
  line-strong: "#d6d0ae"
  rule: "#efebd6"
  stamp: "#c9c4a8"
  ink: "#1c2340"
  muted: "#5f6585"
  white: "#ffffff"
  red: "#c42b3b"
  red-bg: "#fdf1f2"
  red-line: "#f3c7cc"
  red-on-navy: "#f6a3ab"
  green: "#2f7d32"
  amber: "#8a5a12"
  amber-bg: "#fbf3e4"
  amber-line: "#ecd3a4"
  amber-on-navy: "#f2c879"
typography:
  display:
    fontFamily: "Figtree Variable, Manrope Variable, ui-sans-serif, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.25
  headline:
    fontFamily: "Figtree Variable, Manrope Variable, ui-sans-serif, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.55
  title:
    fontFamily: "Figtree Variable, Manrope Variable, ui-sans-serif, sans-serif"
    fontSize: "15px"
    fontWeight: 700
  body:
    fontFamily: "Manrope Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.43
  body-small:
    fontFamily: "Manrope Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
  numeral:
    fontFamily: "Figtree Variable, Manrope Variable, ui-sans-serif, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    fontFeature: "tnum"
  label:
    fontFamily: "Figtree Variable, Manrope Variable, ui-sans-serif, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "0.08em"
  stamp:
    fontFamily: "Figtree Variable, Manrope Variable, ui-sans-serif, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.1em"
  wordmark:
    fontFamily: "Libre Baskerville, Georgia, serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.25em"
rounded:
  stamp: "4px"
  sm: "4px"
  md: "6px"
  lg: "8px"
  full: "9999px"
spacing:
  "1": "4px"
  "1.5": "6px"
  "2": "8px"
  "2.5": "10px"
  "3": "12px"
  "4": "16px"
  "6": "24px"
  "7": "28px"
components:
  button-primary:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.white}"
    typography: "{typography.title}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.navy-2}"
  button-primary-active:
    backgroundColor: "{colors.navy-3}"
  button-beige:
    backgroundColor: "{colors.beige}"
    textColor: "{colors.navy}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "40px"
  button-beige-hover:
    backgroundColor: "{colors.beige-2}"
  button-beige-active:
    backgroundColor: "{colors.beige-3}"
  button-quiet:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "40px"
  button-quiet-hover:
    backgroundColor: "{colors.cream}"
  button-quiet-active:
    backgroundColor: "{colors.cream-2}"
  button-danger:
    backgroundColor: "{colors.white}"
    textColor: "{colors.red}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "40px"
  button-danger-hover:
    backgroundColor: "{colors.red-bg}"
  button-ghost:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.white}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "40px"
  button-ghost-hover:
    backgroundColor: "{colors.navy-2}"
  button-sm:
    padding: "0 12px"
    height: "32px"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "6px 10px"
  field-label:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
  chip:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    typography: "{typography.body-small}"
    rounded: "{rounded.full}"
    padding: "0 12px"
    height: "32px"
  chip-hover:
    backgroundColor: "{colors.cream}"
  chip-selected:
    backgroundColor: "{colors.navy-2}"
    textColor: "{colors.white}"
  stamp-verified:
    backgroundColor: "{colors.white}"
    textColor: "{colors.navy}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "4px 8px"
  stamp-sent:
    backgroundColor: "{colors.white}"
    textColor: "{colors.green}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "4px 8px"
  stamp-needs:
    backgroundColor: "{colors.white}"
    textColor: "{colors.red}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "4px 8px"
  stamp-draft:
    backgroundColor: "{colors.white}"
    textColor: "{colors.muted}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "4px 8px"
  rail-row:
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "8px 10px"
  rail-row-selected:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.white}"
  table-container:
    backgroundColor: "{colors.white}"
    rounded: "{rounded.lg}"
  table-header:
    backgroundColor: "{colors.head}"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    padding: "10px 12px"
  table-row:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    padding: "11px 12px"
  table-row-hover:
    backgroundColor: "{colors.cream}"
  table-row-selected:
    backgroundColor: "{colors.select}"
  note-red:
    backgroundColor: "{colors.red-bg}"
    textColor: "{colors.red}"
    typography: "{typography.body-small}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  note-amber:
    backgroundColor: "{colors.amber-bg}"
    textColor: "{colors.amber}"
    typography: "{typography.body-small}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  note-info:
    backgroundColor: "{colors.cream}"
    textColor: "{colors.ink}"
    typography: "{typography.body-small}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  top-bar:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.white}"
    padding: "0 28px"
    height: "64px"
  avatar:
    backgroundColor: "{colors.beige}"
    textColor: "{colors.navy}"
    rounded: "{rounded.full}"
    size: "28px"
---

# Design System: Meeting Calendar Sync

## Overview

**Creative North Star: "The Stamped Itinerary"**

Meeting Calendar Sync wears the Woodline Partners house colours (taken from woodlinepartners.com) as a quiet internal desk: a navy bar across the top, a cream ground, a cream-2 rail, and white tables ruled in beige hairlines. It is a working surface for a coordinator who checks sixty meetings in one sitting, so density is high. Most text is 13 to 15px, rows are compact, and every number is set in tabular Figtree so the columns read as a timetable rather than prose.

The world borrows its character from the airline ticket wallet and the split-flap board. Columns sit at fixed widths and never move, rows rank by time, and state lives in small letter-spaced stamps that sit on white chips and tilt three degrees when a person has acted on them (VERIFIED, SENT). Untouched states (DRAFT) and cancelled ones lie flat, and cancelled meetings are struck through instead of vanishing. The one authored motion is the stamp landing; everything else changes colour in 150ms and stays put.

Depth is flat. Surfaces are separated by tone (navy, cream, cream-2, white) and 1px warm hairlines; soft navy-tinted shadows appear only on layers that float above the layout. The app has no photography and no hero banners. It must never read as a marketing site.

**Key Characteristics:**
- Navy bar, cream ground, cream-2 rail, white tables with beige hairlines.
- Figtree for headings, numbers, labels and stamps; Manrope for running UI text; Libre Baskerville only in the WOODLINE wordmark.
- Tilted stamps for states a person earned; flat stamps for states nobody has acted on yet.
- Fixed-width columns that line up from day to day; nothing disappears, it gets struck.
- Flat at rest; shadows only on floating layers.

## Colors

Woodline's navy-and-cream palette, with a warm beige for action and highlight, and low-saturation status tints that keep their contrast on cream and white.

### Primary
- **Woodline Navy** (navy): The top bar, page headings, selected colleague in the rail, the primary button, the focus ring on light grounds, and the outline round the highlighted PDF row. Presses darken to Pressed Navy (navy-3); hovers and the selected chip lift to Lifted Navy (navy-2), which also fills badges and inline editors on the bar.
- **Ledger Blue** (blue): Tickers, day headings above each timetable, the revision strip's file icon, and quiet text links ("Keep it separate"). Never a fill.

### Secondary
- **Woodline Beige** (beige): The forward action on navy (Verify all ready) and on the revision strip (Accept all), colleague avatars, the active-nav underline, text selection, and the 60% multiply highlighter over the matched PDF row. Hover goes lighter (beige-2), press goes deeper (beige-3). On navy it is also the focus-ring colour and the colour of counts in a selected rail row or chip.

### Tertiary
- **Stamp Green** (green): SENT stamps and "On X's calendar" confirmations only. It always sits on white (4.5:1 on the selected tint alone is too close).
- **Flag Red** (red): NEEDS stamps, blocking counts, error borders on fields, the danger button. Paired with red-bg and red-line for tinted notes; red-on-navy is its twin on the bar.
- **Warning Amber** (amber): Warning triangles, warning counts, "Removing from…" lines, amber notes (with amber-bg and amber-line). amber-on-navy is its twin for a selected rail row's dot and the bar's retry state.

### Neutral
- **Ledger Cream** (cream): The page ground; also the hover fill for quiet buttons, chips, and table rows.
- **Rail Cream** (cream-2): The colleague rail, the revision strip, the hosted-demo note, PDF loading frame, quiet-button press.
- **Header Cream** (head): The ground of every table header row.
- **Selected Row Tint** (select): A cool pale blue for the selected timetable row, the only cool neutral in the palette.
- **Warm Hairline** (line): Borders on tables, cards, inputs, chips, quiet buttons, panel edges. line-strong is the hover border and switch track; rule is the fainter hairline between table rows.
- **Stamp Grey** (stamp): The border of flat stamps (DRAFT, CANCELLED) and the scrollbar thumb.
- **Skeleton** (skeleton): Loading placeholders, which hold still.
- **Ink** (ink): Body text. **Muted Slate** (muted): secondary text, labels, placeholders, zero counts.
- **White** (white): Tables, panels, inputs, stamp chips, text on navy.

### Named Rules
**The One Beige Action Rule.** A beige fill marks the single forward action of its band: Verify all ready on the bar, Accept all on the revision strip. One per band; everything else is quiet or ghost.

**The Navy-Means-Here Rule.** Where the user is shows in navy: the selected rail row is filled navy, the selected chip navy-2, the active nav link carries a beige underline, and the focus ring is a 2px navy outline (beige on navy).

**The On-Navy Twin Rule.** On the navy bar, status colours switch to their twins (red-on-navy, amber-on-navy) and focus rings switch to beige. Base red, amber and navy outlines never sit on navy.

## Typography

**Display Font:** Figtree Variable (with Manrope Variable, ui-sans-serif)
**Body Font:** Manrope Variable (with ui-sans-serif, system-ui)
**Wordmark Font:** Libre Baskerville 400 (with Georgia)

**Character:** Figtree carries everything that is read as a figure or a heading: names, times, counts, tickers, stamps, column labels. Manrope carries the running UI text at medium and semibold weights. The Baskerville wordmark is the only serif and the only link to Woodline's printed identity.

### Hierarchy
- **Display** (700, 28px, 1.25): The one page heading in the main column: the colleague's name on Review, "Conferences", "Roster", "What changed in revision N". Navy.
- **Headline** (700, 18px): Section headings on the Conferences page (upload, list). Navy.
- **Title** (700, 15px): Panel and popover headings ("Outlook calendars", "Conference timezone", "Add meeting"), and button text at 14px. Navy.
- **Body** (500, 14px, 1.43): Table cells, inputs, rail rows (600), empty states at 15px.
- **Body small** (500 to 600, 13px): Executives line, shared-with column, chips, notes, the summary next to the heading.
- **Numeral** (700, tabular): Every time, count and total, in Figtree. Times are 14px; tickers are 11px in Ledger Blue beside the company.
- **Label** (700, 11px, 0.08em, uppercase): Table column headers in Figtree; field labels in Manrope at 0.06em. Section labels (rail "Colleagues", "Source · file · page") go to 12px at 0.1em; day headings to 13px in Ledger Blue.
- **Stamp** (700, 11px, 0.1em, leading 1): Stamp text, always uppercase by content.

### Named Rules
**The Figtree Figures Rule.** Any number a coordinator compares (time, count, total, ticker) is Figtree bold with tabular figures, so columns of figures align.

**The Wordmark-Only Serif Rule.** Libre Baskerville appears only in the WOODLINE wordmark (uppercase, 0.25em tracking). No other heading, label or number uses it.

## Layout

The app is a fixed-height shell: a navy bar at least 64px tall with 28px side padding, an optional cream-2 strip beneath it, and a main area. Conferences and Roster scroll as pages; Review does not scroll as a page. Its three columns scroll on their own: a 250px colleague rail, a fluid itinerary column (28px gutters, 22px top), and a 400px white source panel with 22px padding.

Responsive behaviour is driven by two named breakpoints. Below 1281px (panel) the source panel becomes a 420px drawer that slides in from the right. Below 901px (rail) the rail becomes a select above the chips. The bar tightens in steps (1680, 1366, 1280px), moves page context to a second row below 1024px, and keeps only the mark below 640px. The timetable is a container-query component: when its column is under 616px (38.5rem), or the window is under 901px, each row stacks into a three-area grid of time, company over room and colleagues, and status.

Spacing runs on a 4px base. 8px and 12px are the working gaps inside controls and cells, 16px to 24px separate blocks, and 28px is the page gutter. Timetable cells pad 11px by 12px; header cells 10px by 12px.

## Elevation & Depth

The system is flat at rest. Depth comes from tonal layering (navy bar over cream ground, cream-2 rail beside it, white tables and panels on top) and from 1px warm hairlines. Shadows are always navy-tinted (rgba of #182958), never grey or black, and appear only on layers that float above the layout.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 8px 24px rgba(24,41,88,0.18)`): Popovers and the source-panel drawer.
- **Bubble** (`box-shadow: 0 4px 12px rgba(24,41,88,0.18)`): An inline editor's error bubble under the field.
- **Toast** (`box-shadow: 0 4px 12px rgba(24,41,88,0.25)`): The ink-filled sync toast at the bottom of the itinerary.
- **Paper** (`box-shadow: 0 1px 3px rgba(24,41,88,0.14)`): The rendered PDF page sitting in its cream-2 frame.
- **Knob** (`box-shadow: 0 1px 2px rgba(24,41,88,0.3)`): The white knob of the roster switch.

### Named Rules
**The Floating-Only Shadow Rule.** If it sits in the layout, it has a hairline and no shadow. A shadow means the layer floats above something (popover, drawer, toast, bubble), or it is a physical object in the scene (the PDF page, the switch knob).

## Shapes

Corners are small and squared off. Controls (buttons, inputs, notes, the PDF frame) take a 6px radius. Containers (timetable cards, empty states, popovers, rail rows) take 8px. Pills (filter chips, avatars, config badges, flag dots, the switch) are fully round. Stamps are 4px with a 1.5px border. Focus outlines and text links use 4px. Borders are 1px hairlines everywhere except stamps (1.5px) and the PDF highlight outline (2px navy). Strikethroughs on cancelled times and stamps are 1.5px thick.

The mark is Woodline's two-chevron emblem, drawn as inline SVG in currentColor.

## Components

### Buttons
Compact and confident: bold Figtree text, solid fills, no shadow.
- **Shape:** Gently squared (6px). Medium is 40px tall with 16px sides and 14px text; small is 32px tall with 12px sides and 13px text; the icon size is 32px square.
- **Primary:** Navy fill, white text. Hover navy-2, press navy-3.
- **Beige:** Beige fill, navy text, beige focus ring. Reserved for the forward action of a band (see The One Beige Action Rule). On the cream-2 strip it gains a beige-3 border and a navy focus ring.
- **Quiet (default):** White fill, warm hairline border, ink text. Hover cream with a line-strong border, press cream-2.
- **Danger:** White fill, red-line border, red text. Hover fills red-bg with a red border. Destructive actions use the two-step confirm button: a quiet button that turns danger and reads "Delete for good?" for four seconds. No modal.
- **Ghost (on navy):** Transparent with a 35% white hairline, white text. Hover fills navy-2.
- **States:** Colour transitions take 150ms ease-out. Disabled is 50% opacity. Loading swaps the icon for a spinning loader and keeps full opacity.

### Chips
- **Style:** Status filter pills 32px tall, 12px sides, 13px semibold text, white with a warm hairline, each with a Figtree tabular count.
- **State:** Selected fills navy-2 with white text and a beige count. Unselected counts turn red (needs attention) or amber (warnings) when non-zero and muted when zero. Hover cream.

### Stamps (signature)
The state of every meeting, stamped on a white chip: 11px Figtree bold, 0.1em tracking, 1.5px border in the text colour, 4px radius, 4px by 8px padding.
- **Tilted (-3deg):** VERIFIED navy, SENT green with an inline check icon, NEEDS … red, amber variants.
- **Flat:** DRAFT in muted text with a stamp-grey border; CANCELLED the same but struck through.
- **Landing:** When a meeting becomes VERIFIED or SENT on screen, the stamp comes down 8% large at -6deg and settles to -3deg in 200ms on `cubic-bezier(0.16, 1, 0.3, 1)`. Stamps already in that state on load lie still. This is the one authored motion in the app.

### Cards / Containers
- **Corner Style:** 8px.
- **Background:** White on the cream ground.
- **Shadow Strategy:** None (see The Floating-Only Shadow Rule).
- **Border:** 1px warm hairline.
- **Internal Padding:** 24px by 32px for empty states; tables clip to the card with no inner padding.

### Inputs / Fields
- **Style:** White, 1px warm hairline, 6px radius, 6px by 10px padding, 14px medium ink text, navy caret, muted placeholder.
- **Focus:** Border turns navy plus a 2px navy outline at 1px offset.
- **Error / Disabled:** Error turns the border red, and an inline editor's message floats below in a red-bg bubble. Disabled is 60% opacity.
- **Labels:** 11px bold uppercase muted labels with 0.06em tracking sit 4px above the field.
- **Inline edit:** Values read as plain text and become an input on click (hover cream on light grounds, navy-2 on the bar). Enter or blur saves; Esc cancels.

### Navigation
- **Top bar:** Navy, at least 64px tall. The chevron mark and WOODLINE wordmark come first, then the product name in 15px semibold at 85% white, then page context. Nav links are 14px semibold at 75% white. Hover goes full white with a faint underline; the active link is white with a 2px beige underline at a 7px offset. Config badges are navy-2 pills with beige icons.
- **Colleague rail:** cream-2 column with an uppercase muted section label. Each row has a 28px beige avatar with navy initials, the name, an optional 8px flag dot, and a right-aligned Figtree count. Hover tints the row beige at 45%. The selected row fills navy with white text, a beige count and on-navy dot colours. Arrow keys move and select. Below 901px the rail becomes a select.

### Timetable (signature)
One white, hairline-bordered 8px card per day, headed by a 13px uppercase Ledger Blue day label. Columns have fixed widths so they line up from day to day: Time 116px, Company fluid, Room 104px, Shared with 136px, Status 128px. Header cells use the label style on the header-cream ground. Each row shows the start time in bold Figtree (plus a small select-tint zone tag such as CT when the meeting has its own timezone), with the end time and the viewer's local-time hint in 12px muted text underneath; the company in bold with its ticker in blue beside it; and the executives and format in 13px muted text. Rows are separated by rule-coloured hairlines, hover cream, and turn the select tint when selected. Cancelled rows go muted and struck through but stay in place. Rows stack below 616px of column width (see Layout).

### Notes
Tinted inline notes with a 1px border, 6px radius, 10px by 12px padding and 13px semibold text, with a 16px icon. Red (red-bg, red-line) is for what blocks verifying; amber is for what to check; cream with a hairline is for plain information.

### Source highlight
The matched PDF row is marked like a highlighter: beige at 60% with `mix-blend-mode: multiply`, so the printed text stays black, plus a 2px navy outline.

## Do's and Don'ts

### Do:
- **Do** separate surfaces by tone and 1px warm hairlines (line, rule) rather than shadows.
- **Do** set every time, count, total and ticker in Figtree bold with tabular figures.
- **Do** tilt a stamp (-3deg) only for a state a person acted on, and keep DRAFT and CANCELLED flat.
- **Do** put every stamp on a white chip so green and red keep their contrast on the select tint.
- **Do** strike cancelled meetings through (1.5px) and leave them in place; nothing disappears.
- **Do** keep timetable columns at fixed widths so days line up, and let rows stack only below 616px of column width.
- **Do** use the on-navy twins (red-on-navy, amber-on-navy) and a beige focus ring on the navy bar.
- **Do** use inline SVG icons (lucide line icons, 2 to 3px stroke) for checks, warnings and actions.
- **Do** keep transitions to 150ms ease-out colour changes, and honour reduced motion (stamps and reveals stop, transitions collapse).

### Don't:
- **Don't** use photos, hero banners or marketing-page composition; this is an internal Operate tool.
- **Don't** use Libre Baskerville outside the WOODLINE wordmark.
- **Don't** put more than one beige-filled button in a band.
- **Don't** add shadows to resting cards, tables, chips or buttons; and never use grey or black shadows.
- **Don't** animate beyond the stamp landing, the revision-strip reveal and the extraction progress sweep; loading skeletons hold still.
- **Don't** use typed glyphs (✓, →) for status or icons; the check in SENT is an SVG.
- **Don't** introduce new radii; use 4px (stamps, focus), 6px (controls), 8px (containers) or a full pill.
