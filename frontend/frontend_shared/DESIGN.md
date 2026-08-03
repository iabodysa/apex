# Portal design guide

A developer joining Apex reads this once and can then add a screen to any portal without
asking anyone where things go. It is a contract, not advice: where it gives a number, that
number is already in `tokens.css` or in a shared shell, and a screen that disagrees with it
is the thing that is wrong.

## 1. Page anatomy

Every portal page is the same four parts in the same order. They are not optional, and no
page invents a fifth.

```
┌──────────────────────────────┐
│ HEADER      sticky, 1 row    │  who you are · where you are · at most 2 actions
├──────────────────────────────┤
│ FRAME                        │  the only element that scrolls
│   ┌──────────────────────┐   │
│   │ CARD                 │   │  one subject per card
│   └──────────────────────┘   │
│   ┌──────────────────────┐   │
│   │ CARD                 │   │
│   └──────────────────────┘   │
├──────────────────────────────┤
│ NAVBAR      sticky bottom    │  3–5 destinations, never actions
└──────────────────────────────┘
```

**Header.** Sticky, one row, `14px 20px 16px`. It carries the person's name or the record's
title on the reading side, and at most two actions on the far side. It never carries the
primary action of the page, never a filter, never a search field that only one screen uses.
A second header row is allowed for progress only.

**Frame.** `padding: 16px`, and it owns the scroll — `overflow-y: auto` lives here and
nowhere else. Two nested scrollers is the defect that makes a phone feel broken. Maximum
width by archetype in §3.

**Card.** Radius `--radius` (12px), `--sp-4` (16px) padding, `--c-surface-2` ground,
`--c-border` edge, `--shadow-sm`. One subject per card, one primary action per card. A card
that holds two unrelated things is two cards. A list row is not a card: rows sit inside one
card with `--c-border` dividers.

**Navbar.** Sticky to the bottom on a phone, 3–5 items, each `--tap-lg` (52px) tall, with
`env(safe-area-inset-bottom)` respected. Destinations only — never Save, never Submit, never
Delete. The active item carries both `class="is-active"` and `aria-current="page"`.

**Footer.** There is none. A portal page ends at its navbar. Legal text, version and build
id belong on the account screen, one per portal.

## 2. The hot zone

A worker holds the phone in one hand and reaches with a thumb. That divides the screen into
three bands, and the band decides what may live there.

```
┌──────────────────────────────┐  ← top 25%: hard to reach
│  title · status · read-only  │     nothing tappable that matters
├──────────────────────────────┤
│  content, scrollable         │  ← middle: comfortable
│                              │
├──────────────────────────────┤  ← bottom 33%: the hot zone
│  primary action · navbar     │     everything used often
└──────────────────────────────┘
```

- The page's primary action sits at the bottom of the frame, full width, `--tap-lg`, above
  the navbar. It does not scroll away.
- A destructive action (delete, reject, cancel a trip) is **never** in the hot zone. Put it
  in an overflow menu or behind a confirm sheet — a thumb resting at the bottom of the screen
  must not be able to destroy a record by accident.
- The top band takes the title, the status pill, the sync indicator: things that are read,
  not pressed.
- Back is top-start; it is the one exception, because every platform puts it there and muscle
  memory beats reach.

## 3. Element distribution

The archetype decides the grid. There are three, and every portal is exactly one.

### Field worker — `/driver`, `/masar`, `/housing`, `/safety`

One task at a time, standing, one hand, often offline. Shell: `MobileConsoleShell.vue` —
used today by `/driver` and `/masar` only. `/housing` and `/safety` hand-roll the same
skeleton, which is why a fix to the shell reaches two of the four; folding them onto it is
part of the work this guide sets up.

| Width | Frame | Layout |
| --- | --- | --- |
| < 480 | 100% | one column, cards stacked, bottom navbar |
| 480–1023 | `min(100%, 560px)` centred | same column, larger type, cards gain breathing room |
| ≥ 1024 | `min(100%, 1100px)` centred | **two panes**: list on the reading side (360–420px), detail filling the rest; navbar moves to a side rail |

**The open defect this guide exists to fix.** Today these four portals draw the same ~480px
column at 1440px and leave two thirds of the screen empty (`_staging/evidence/viewports/driver-desktop.png`).
That is not "mobile first", it is one layout pretending to be responsive. The desktop row
above is the contract; the shell has to grow to meet it.

### Supervisor — `/masar-supervisor`

Decides about other people's work: approves, assigns, watches. Shell:
`TabletSupervisorShell.vue`.

| Width | Layout |
| --- | --- |
| < 1024 | one pane at a time, list first, back control on the detail, top bar replaces the side-nav |
| ≥ 1024 | fixed side-nav (240px) with sections and live counts · list (340–400px) · detail (fills) · optional third pane for a map or a queue |

Every pane is addressable — `#/plan/:name`, `#/map`, `#/approvals` — so a supervisor can send
a link and the receiver lands on the same pane.

### Operations board — `/fleet-os`, `/fleet`

Scans many rows for the exception. Density is the point. Shell: `FleetPageShell.vue`.

| Width | Layout |
| --- | --- |
| < 1024 | filters in a sheet behind one button, results full width |
| ≥ 1024 | permanent filter rail (300px) on the inline-start edge · results filling the rest, with a view switcher that survives a reload |

## 4. Text

Words are interface, and they follow the same rules everywhere.

- **Labels name what the person controls**, never what the system stores: the plate number,
  not `vehicle_id`. A label is a noun phrase, sentence case, no colon, no trailing period.
- **Buttons are verbs, and the verb never changes** between the button, the confirm and the
  toast: an Approve button produces an Approved toast, in whatever language the portal is in.
  A button that says one thing and reports another teaches the person that the interface lies.
- **One job per element.** A label labels; a hint gives an example; a placeholder is not a
  label and never carries required information.
- **Errors say what happened and what to do**, in the interface's voice, with no code and no
  apology: "the trip has started, so its stops can no longer be changed" beats "error 417".
- **Empty is an invitation**, not a status: "no requests today — start one" beats "no data".
- **Numbers stay LTR inside an Arabic line** — plate codes, timestamps, ids — wrapped in
  `<bdi>`, never by forcing the paragraph's direction.
- **No string lives in a component.** Portal strings come from `frontend/*/src/i18n.js`, desk
  strings from `apex/translations/ar.csv`, and the two never mix. An English label on an
  Arabic screen is a defect, not a fallback.

## 4b. Controls come from the library

`frappe-ui` is the toolkit, not a dependency to ration. Every control a screen needs —
button, dialog, select, autocomplete, form control, error message, badge, avatar, list view,
tabs, switch, checkbox, text input, textarea, date picker, progress, alert, tooltip,
dropdown, breadcrumbs, toast, chart — comes from it, with its own behaviour and its own
structure. Its calls (`createResource`, `createListResource`) are how a screen reads.

Hand-write a control only where the library has nothing that fits, and record which
component you looked for. The tokens in §8 still decide colour, spacing and tap size: pass
them into the component rather than restyling or forking it.

## 5. Icons

- One set: `IconBase.vue` + `icons.js` for Apex glyphs, and whatever `frappe-ui` already
  draws for the controls it owns. A portal that inlines an SVG has left the system.
- Three sizes only: 16 beside text, 20 in a control, 24 alone in a tap target.
- `currentColor` always, so an icon inherits its context and both themes work with no second
  asset.
- **An icon alone is allowed only where the meaning is unambiguous and repeated** — back,
  close, search, add. Everything else carries a label. An icon-only button still needs
  `aria-label`, and its tap target is still 44px even when the glyph is 20.
- Direction icons flip in RTL (back, next, trend); object icons do not (a vehicle, a
  building, a bed).
- An icon never carries state alone. Colour plus glyph, or glyph plus text — never colour
  alone, because a colour-blind reader and a printed screenshot both lose it.

## 6. Ease of use

Testable rules, not sentiment.

- **The main task of a screen is reachable in one tap from that portal's landing screen.**
  If it takes three, the navigation is wrong.
- **The screen survives a reload.** The route, the open pane, the chosen filter and the
  scroll position come back. A supervisor who refreshes must not lose their place.
- **Nothing moves after it is drawn.** A skeleton occupies the shape the content will take;
  a page that jumps when data lands has no skeleton.
- **Every wait is visible within 300ms** and every action reports its result — a toast for
  success, an inline message for a failure that the person can fix.
- **A form never loses input.** Navigating away asks, and a failed submit keeps the values.
- **Offline is a state, not an error.** The worker portals queue and say so; they do not show
  a network stack trace.
- **Keyboard and screen reader**: focus order follows the reading order, focus is visible
  with the single `--focus` ring, and a dialog traps focus and returns it on close.

## 7. Component states

Every list, form and panel declares all four. A screen that draws only its happy path is not
finished.

| State | What ships |
| --- | --- |
| Loading | a skeleton of the shape that is coming — never a spinner alone |
| Empty | `EmptyState.vue`: icon, what is missing, what to do, and the action if allowed |
| Error | what failed in the reader's terms, and a retry |
| Disabled | the control stays visible in `--c-muted` with the reason beside it |

## 8. Tokens, scales, targets

Never write a colour, radius, gap or font size as a literal. The only names a portal uses are
the `--c-*` aliases.

| Role | Token | Light (afmco) | Dark |
| --- | --- | --- | --- |
| Page ground | `--c-canvas` | `#e9e3d3` | `#0b110e` |
| Raised sheet | `--c-surface` | `#f8f5ee` | — |
| Card | `--c-surface-2` | `#ffffff` | — |
| Body ink | `--c-ink` | `#072b1a` | `#e7efe9` |
| Secondary ink | `--c-muted` | `#586962` | — |
| Primary fill | `--c-primary` | `#00844e` | — |
| Ink on primary | `--c-primary-ink` | `#ffffff` | — |
| Divider | `--c-border` | `#ddd5c2` | — |
| Control edge | `--c-border-control` | `#8d8168` | — |
| Success | `--c-success` / `-bg` | `#046b41` / `#d9f0e3` | — |
| Warning | `--c-warning` / `-bg` | `#8a5a10` / `#f7ead2` | — |
| Danger | `--c-danger` / `-bg` | `#a52d21` / `#f6dcd8` | — |
| Focus ring | `--focus` | `#046b41` | — |

Two themes exist and only two — `afmco` and `dark` — both declared in `tokens.css` and
nowhere else. The server writes the choice onto `<html data-theme>`; a portal never picks its
own. Contrast ratios are recorded beside each value in `tokens.css`; a new colour records its
ratio there too.

**Type** `--fs-display` 28 · `--fs-h1` 22 · `--fs-h2` 20 · `--fs-h3` 16 · `--fs-body` 14 ·
`--fs-sm` 13 · `--fs-xs` 11 · `--fs-2xs` 10 (dense table headers only; nothing a worker reads
on a phone goes below `--fs-sm`).

**Spacing** `--sp-1` 4 · `--sp-2` 8 · `--sp-3` 12 · `--sp-4` 16 · `--sp-5` 20 · `--sp-6` 24 ·
`--sp-8` 32. **Radius** `--radius-sm` 8 · `--radius` 12 · `--radius-lg` 18 · `--radius-pill`
999.

**Tap targets** `--tap-lg` 52 primary and navbar · `--tap-md` 48 ordinary control ·
`--tap-min` 44 floor, in both dimensions, icon-only included.

**Breakpoints** `--bp-phone` 480 · `--bp-tablet` 768 · `--bp-wide` 860 · `--bp-desktop` 1024.
A media query cites the token it mirrors in a comment; the pixel is duplicated only because
CSS cannot use a custom property in a query.

## 9. RTL

Arabic is the primary direction and English is the exception.

- Logical properties only — `margin-inline-start`, `padding-inline-end`, `inset-inline-start`
  — never `left` / `right`. **The one exception**: an element positioned with a `transform`
  does not flip, so pair it with physical `left` / `top`. This has bitten us: an overlay
  pinned with `inset-inline-start` plus `translate` landed off-canvas in RTL.
- A date input renders in the browser's locale, so `mm/dd/yyyy` appears under an Arabic
  label. Use the shared picker or set `lang` explicitly.
- Test at 390px in RTL before you call a screen done; most RTL breakage is invisible at
  desktop width.

## 10. Adding a screen — the checklist

1. Name the archetype. Import that shell; do not build a layout.
2. Put the primary action in the hot zone and destructive actions out of it.
3. Take every colour, size and gap from §8. Zero literals.
4. Write the four states before the happy path is finished.
5. Every string through the portal's `i18n.js`.
6. Icons from `icons.js`, labelled unless the meaning is one of the four unambiguous ones.
7. Make the route addressable and reload-safe.
8. Check at 390, 834 and 1440, in both directions and both themes.
9. Reach for what exists first, in this order: a `frappe-ui` component, then the shared
   layer here — `EmptyState`, `Brand`, `LangToggle`, `ThemeToggle`, `IconBase`,
   `BuildingPicker`, `useToast`, `useOverlay`, `usePoll` — and only then your own. A
   hand-rolled control that the library already ships is a defect.
