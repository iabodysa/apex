# Portal design guide

What a builder needs to put a screen on any Apex portal without inventing a value. Every
number below is the one `tokens.css` already declares; where a portal disagrees with this
page, the portal is wrong.

Read it with the captures beside it: `_staging/evidence/viewports/` holds each portal at
1440, 834 and 390 CSS pixels, which is where the layout claims below come from.

## The three archetypes

Each portal belongs to exactly one, and the archetype decides the layout — not the module it
belongs to.

### 1. Field worker — phone first, one column

`/driver`, `/masar`, `/housing`, `/safety`.

Someone standing, one-handed, often on a poor connection, doing one task at a time. One
column, large tap targets, no chrome that is not the task. The shell is
`MobileConsoleShell.vue`.

- Column: `min(100%, var(--bp-phone))` centred, `--sp-4` gutters.
- Primary action: `--tap-lg` (52px), full width, at the bottom of the visible area.
- Body text never below `--fs-body` (14px); numbers a supervisor reads at arm's length use
  `--fs-h1` (22px).
- **Open defect, and the reason this guide exists.** At 1440px these portals still draw the
  same 480px column and leave the rest of the screen empty (see `driver-desktop.png`). A
  field portal opened on a desk machine must widen to the reading column at `--bp-tablet`
  and, past `--bp-desktop`, put the list beside the detail rather than centring one narrow
  strip. Until that lands, do not describe these portals as responsive.

### 2. Supervisor — sidebar, list, detail

`/masar-supervisor` (the route supervisor board). The reference implementation; copy this
one.

- Past `--bp-desktop` (1024px): a fixed side-nav carrying sections and live badge counts, and
  a work area of up to three panes — list, detail, and a map or a queue.
- Below it: the side-nav collapses to a top bar, and the work area shows one pane at a time,
  list first, with a back control on the detail.
- Every route is addressable (`#/plan/:name`, `#/map`, `#/approvals`) so a supervisor can
  send a link to a colleague and land on the same pane.
- Shell: `TabletSupervisorShell.vue`.

### 3. Operations board — filter rail and dense grid

`/fleet-os`, `/fleet`.

Someone scanning many rows for the exception. Density beats whitespace here, and the filters
are permanent furniture, not a drawer.

- Filter rail on the inline-start edge at `--bp-desktop` and wider, collapsing to a sheet
  below it.
- A view switcher (cards / table / grouped / compact) that survives a reload.
- Column headers at `--fs-2xs`, uppercase, `--c-muted`.
- Shell: `FleetPageShell.vue`.

## Tokens

Never write a colour, a radius or a gap literal in a portal. The only names a portal may use
are the `--c-*` aliases; the raw palette below exists so this page can say what they resolve
to, and it changes with the theme.

| Role | Token | Light (afmco) | Dark |
| --- | --- | --- | --- |
| Page ground | `--c-canvas` | `#e9e3d3` | `#0b110e` |
| Raised sheet | `--c-surface` | `#f8f5ee` | — |
| Card / control | `--c-surface-2` | `#ffffff` | — |
| Body ink | `--c-ink` | `#072b1a` | `#e7efe9` |
| Secondary ink | `--c-muted` | `#586962` | — |
| Primary fill | `--c-primary` | `#00844e` | — |
| Ink on primary | `--c-primary-ink` | `#ffffff` | — |
| Divider | `--c-border` | `#ddd5c2` | — |
| Control edge | `--c-border-control` | `#8d8168` | — |
| Success | `--c-success` / `--c-success-bg` | `#046b41` / `#d9f0e3` | — |
| Warning ink | `--c-warning` / `--c-warning-bg` | `#8a5a10` / `#f7ead2` | — |
| Danger | `--c-danger` / `--c-danger-bg` | `#a52d21` / `#f6dcd8` | — |
| Focus ring | `--focus` | `#046b41` | — |

Two themes exist and only two: `afmco` (light, the default identity) and `dark`. Both are
declared in `tokens.css` and nowhere else; a portal that declares its own `--c-*` block has
left the system. The theme arrives as `data-theme` on `<html>`, written by the server from
the Portal Theme setting, so a portal never chooses its own.

Contrast is not a matter of taste here: every pair above is checked, and the ratio is written
beside the value in `tokens.css`. If you introduce a colour, put its ratio there too.

## Type scale

`--fs-display` 28 · `--fs-h1` 22 · `--fs-h2` 20 · `--fs-h3` 16 · `--fs-body` 14 · `--fs-sm`
13 · `--fs-xs` 11 · `--fs-2xs` 10.

`--fs-2xs` is for table column headers and dense supervisor labels only. Nothing a worker
reads on a phone goes below `--fs-sm`.

## Spacing

`--sp-1` 4 · `--sp-2` 8 · `--sp-3` 12 · `--sp-4` 16 · `--sp-5` 20 · `--sp-6` 24 · `--sp-8`
32. Radii: `--radius-sm` 8 · `--radius` 12 · `--radius-lg` 18 · `--radius-pill` 999.

## Touch targets

`--tap-lg` 52px for a primary action and a bottom-nav item, `--tap-md` 48px for an ordinary
control, `--tap-min` 44px as the floor. Nothing tappable is smaller than 44px in either
dimension, including an icon-only button.

## Breakpoints

`--bp-phone` 480 · `--bp-tablet` 768 · `--bp-desktop` 1024, with `--bp-wide` 860 marking
where a secondary column inside a supervisor work area folds away. A media query must cite
the token it mirrors in a comment; the pixel value is duplicated only because CSS cannot use
a custom property in a query.

## Component states

Every list, form and panel declares all four. A screen that only draws its happy path is not
finished.

- **Loading** — a skeleton of the shape that is coming, never a spinner alone, and never a
  layout that jumps when the data lands.
- **Empty** — `EmptyState.vue`: an icon, a title that says what is missing, a hint that says
  what to do, and the action itself when the reader is allowed to take it. Never the word
  "No data".
- **Error** — what failed, in the reader's terms, and a retry. Never a stack trace, never a
  code alone.
- **Disabled** — the control stays visible with `--c-muted` ink and a reason nearby. A
  control that disappears teaches nothing.

## RTL

Arabic is the primary direction; English is the exception. The rules are absolute:

- Use logical properties — `margin-inline-start`, `padding-inline-end`, `inset-inline-start`
  — never `left` / `right`, except where an element is positioned with a transform, which
  does not flip. That exception has bitten this codebase: an overlay pinned with
  `inset-inline-start` plus `translate` landed off-canvas in RTL and had to move to physical
  `left` / `top`.
- Icons that carry direction (back, next, trend) flip; icons that carry meaning (a vehicle, a
  building) do not.
- Numbers, plate codes and timestamps stay left-to-right inside an RTL line; wrap them in
  `<bdi>` rather than forcing a direction on the paragraph.
- A date input renders in the browser's locale. `mm/dd/yyyy` under an Arabic label is a
  defect (visible today in `/fleet-os`); pass an explicit `lang` or use the shared picker.

## Strings

No Arabic in a component. Portal strings come from `frontend/*/src/i18n.js`, desk strings
from `apex/translations/ar.csv`, and the two never mix. A portal shipping an English label
in an Arabic shell is a bug, not a fallback — `/driver` shows three today ("Salis
Workspace", "Dispatch Board", "Transport Requests") and they are the shape to look for.

## What to reach for before writing anything

`frontend_shared/components/` already ships `EmptyState`, `Brand`, `LangToggle`,
`ThemeToggle`, `IconBase`, `BuildingPicker`, and the three shells named above; `useToast`,
`useOverlay` and `usePoll` cover the behaviour a screen usually needs. A second copy of any
of these is the thing this guide exists to prevent.
