# Apex identity and product system

Open [`index.html`](index.html) for the visual guide. It is Arabic-first, works
offline, and covers identity, product UI, responsive web layouts, RTL,
accessibility, motion, and social formats.

## Concept

The mark is a folded route forming an open `A`. Two operational paths meet at
one apex while the negative space remains an open gateway. It expresses the
product promise: many moving parts, one clear outcome.

The palette is unchanged from
[`frontend/frontend_shared/tokens.css`](../../frontend/frontend_shared/tokens.css).
Forest and warm canvas carry most of the visual weight; green signals action;
mint marks progress and focus.

## Source assets

- `assets/logo/apex-mark.svg` — primary mark on light backgrounds
- `assets/logo/apex-mark-reverse.svg` — mark on forest or dark backgrounds
- `assets/logo/apex-mark-mono.svg` — one-colour production master
- `assets/logo/apex-lockup-ar.svg` — Arabic lockup
- `assets/logo/apex-lockup-en.svg` — English lockup
- `assets/logo/apex-app-icon.svg` — app icon master
- `assets/social/` — editable ratio masters for social channels

Keep SVG files as masters. Export PNG only for channels that cannot accept SVG.
The two lockups embed their approved font subsets, so they render consistently
without installed fonts. Do not rebuild them from arbitrary runtime fonts.

## Product boundary

This guide defines the Apex product identity. Tenant, customer, or operator
logos are co-branding inputs and must not replace the Apex master assets. The
guide does not change portal runtime assets; product rollout is a separate,
reviewable implementation step.

## Implementation source of truth

This guide explains intent and use. Portal code continues to follow
[`frontend/frontend_shared/DESIGN.md`](../../frontend/frontend_shared/DESIGN.md)
and the shipped token file. When prose and code disagree, inspect the live code
and update both in one scoped change.
