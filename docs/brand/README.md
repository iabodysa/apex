# Apex identity and product system

Open [`index.html`](index.html) for the visual guide. It is Arabic-first and
covers identity, product UI, responsive web layouts, RTL,
accessibility, motion, and social formats.

## Concept

The mark is a folded route forming an open `A`. Two operational paths meet at
one apex while the negative space remains an open gateway. It expresses the
product promise: many moving parts, one clear outcome.

The palette is unchanged from the shipped
[`tokens.css`](../../frontend/apex_portal/styles/tokens.css). This source link is
intentional: the runtime token file, not a copied document, is authoritative.
Forest and warm canvas carry most of the visual weight; green signals action;
mint marks progress and focus.

## Source assets

- `assets/logo/apex-mark.svg` — primary mark on light backgrounds
- `assets/logo/apex-mark-reverse.svg` — mark on the forest brand field
- `assets/logo/apex-mark-mono.svg` — one-colour production master
- `assets/logo/apex-lockup-ar.svg` — Arabic lockup
- `assets/logo/apex-lockup-en.svg` — English lockup
- `assets/logo/apex-app-icon.svg` — app icon master
- `assets/social/*.svg` — editable ratio masters for social channels
- `assets/social/*-preview.png` — browser-rendered previews for design handoff
- `assets/imagery/operations-morning.jpg` — synthetic, public-safe imagery specimen

Keep SVG files as masters. Export PNG only for channels that cannot accept SVG.
The Arabic lockup stores the approved Thmanyah wordmark as vector outlines; it does
not redistribute the licensed font. The English lockup embeds its approved subset.
Do not rebuild either lockup from arbitrary runtime fonts.

## Product boundary

This guide defines the Apex product identity. Tenant, customer, or operator
logos are co-branding inputs and must not replace the Apex master assets. The
guide does not change portal runtime assets; product rollout is a separate,
reviewable implementation step.

## Implementation source of truth

This guide explains intent and use. Portal code continues to follow the
[portal implementation contract](portal-design.md), the shipped token file,
and the source-adjacent
[`CONTRACTS.md`](../../frontend/apex_portal/CONTRACTS.md). Component API
contracts stay beside the Vue source so code and contract change together.
When prose and code disagree, inspect the live code and update both in one
scoped change.
