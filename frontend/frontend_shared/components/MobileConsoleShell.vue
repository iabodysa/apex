<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- =====================================================================
     ARCHETYPE 2 — Mobile console (worker · driver · safety · housing).
     One-hand ergonomics: a sticky dark header (greeting + actions + optional
     progress band), a single scrolling column of stacked cards, and a sticky
     bottom nav of AT MOST THREE items at --tap-lg targets with the iOS
     safe-area inset added underneath.

     Consumes ONLY shared --c-* tokens. RTL-first (logical properties).

     COLUMN WIDTH — the shell owns it, not the portal.
       < 768px   480px for all four portals.
       >= 768px  480px by default; a portal that is a reading surface rather
                 than a one-hand task (safety, housing) sets --shell-wide: 720px
                 on the shell and widens only there.
     The width arrives as a CUSTOM PROPERTY, never as an inline max-width: an
     inline style outranks every stylesheet rule, so a shell that set max-width
     inline could never have a working tablet breakpoint. That is why the shipped
     shell had no media query at all.

     THREE TABS, NOT FIVE. A fourth item costs each tab a fifth of a 390px
     screen and the labels start truncating; a phone console that needs a fourth
     destination needs a menu, not a fourth tab.

     SLOTS
       header   — full header content. Or use `title`/`subtitle` props for the
                  default greeting; slot overrides it.
       header-actions — end of the header row (bell, avatar). Ignored if the
                  `header` slot is provided.
       progress — optional band under the header (progress bar, day summary).
       default  — the scrolling content column (portal drops stacked cards).
       nav      — bottom-nav items (three). Any element works: each direct child
                  is auto-sized to an equal-width --tap-lg target. Mark the
                  current one with `class="is-active"` AND `aria-current="page"`.

     PROPS
       title / subtitle — default header greeting text.
       maxWidth — column width (default 480px, the one-hand column).
     ===================================================================== -->
<template>
  <div class="mc-shell" :style="shellVars">
    <header class="mc-head">
      <slot name="header">
        <div class="mc-head-row">
          <div class="mc-greet">
            <small v-if="subtitle">{{ subtitle }}</small>
            <b>{{ title }}</b>
          </div>
          <span class="mc-head-actions"><slot name="header-actions" /></span>
        </div>
      </slot>
      <div v-if="$slots.progress" class="mc-progress"><slot name="progress" /></div>
    </header>

    <main class="mc-scroll"><slot /></main>

    <nav v-if="$slots.nav" class="mc-nav"><slot name="nav" /></nav>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  maxWidth: { type: [Number, String], default: 480 },
});

// Handed to CSS as a custom property so the tablet breakpoint below can still
// widen the column; an inline max-width would out-rank it permanently.
const shellVars = computed(() => ({
  "--mc-width": typeof props.maxWidth === "number" ? props.maxWidth + "px" : props.maxWidth,
}));
</script>

<style scoped>
.mc-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  margin: 0 auto;
  width: 100%;
  max-width: var(--mc-width);
  background: var(--c-surface);
  color: var(--c-ink);
  font-family: var(--font);
  font-weight: var(--fw-body);
}
/* 768px = --bp-tablet, 1024px = --bp-desktop (frontend_shared/tokens.css); keep in sync —
   CSS @media conditions cannot read a custom property. The column grows with the screen
   instead of staying a phone strip in the middle of a monitor; DESIGN.md §3 carries the
   widths. A portal that needs a different one still overrides with --shell-wide. */
@media (min-width: 768px) {
  .mc-shell {
    max-width: var(--shell-wide, 560px);
  }
}
@media (min-width: 1024px) {
  .mc-shell {
    max-width: var(--shell-wide, 640px);
    box-shadow: var(--shadow);
    border-inline: 1px solid var(--c-border);
  }
}

/* ---- sticky header ---- */
.mc-head {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--c-header-bg);
  color: var(--c-header-ink);
  padding: var(--sp-4) var(--sp-5);
}
.mc-head-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.mc-greet {
  min-width: 0;
}
.mc-greet small {
  display: block;
  font-size: var(--fs-sm);
  opacity: 0.72;
}
.mc-greet b {
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
}
.mc-head-actions {
  margin-inline-start: auto;
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
}
/* Tinted from the header ink rather than a literal white, so the band keeps its
   8% lift when the header goes dark instead of staying a light-mode overlay. */
.mc-progress {
  margin-top: var(--sp-4);
  background: color-mix(in srgb, var(--c-header-ink) 8%, transparent);
  border-radius: var(--radius);
  padding: var(--sp-3) var(--sp-4);
}

/* ---- scroll column ---- */
.mc-scroll {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  /* Reaching the end of the column must not start dragging the page behind it —
     one-handed scrolling overshoots constantly. */
  overscroll-behavior: contain;
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

/* ---- bottom nav ---- */
.mc-nav {
  position: sticky;
  bottom: 0;
  z-index: 20;
  display: flex;
  gap: var(--sp-1);
  background: var(--c-surface-2);
  border-top: var(--border-width) solid var(--c-border);
  padding: var(--sp-2) var(--sp-2) calc(var(--sp-2) + env(safe-area-inset-bottom, 0px));
}
/* Each nav item becomes an equal-width --tap-lg target, whatever element it is. */
.mc-nav :slotted(*) {
  flex: 1;
  min-height: var(--tap-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-1);
  text-decoration: none;
  color: var(--c-muted);
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  border: none;
  background: none;
  border-radius: var(--radius);
  cursor: pointer;
  /* No double-tap-to-zoom wait on the one control this user taps most. */
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
@media (hover: hover) {
  .mc-nav :slotted(a:hover:not(.is-active)),
  .mc-nav :slotted(button:hover:not(:disabled):not(.is-active)) {
    color: var(--c-ink-soft);
    background: color-mix(in srgb, var(--c-ink) 6%, transparent);
  }
}
/* The active state cannot be carried by the tint. A tint deep enough to clear 3:1
   against the bar drags the 11px label down with it — at 34% the label measures
   2.94:1, worse than the 4.03:1 it had at 13%. So the tint stays light and the
   state is carried by two things that do not fight each other: --c-accent-ink,
   which exists precisely to sit on a primary tint (5.58:1 light, 6.27:1 dark), and
   a weight change, which survives with no colour perception at all. */
.mc-nav :slotted(.is-active),
.mc-nav :slotted([aria-current="page"]) {
  color: var(--c-accent-ink);
  background: color-mix(in srgb, var(--c-primary) 13%, transparent);
  font-weight: var(--fw-heading);
}
/* Two of the eight mandatory states. A tab that cannot be opened yet (no trip
   started, no building picked) must say so rather than silently no-op, and the
   keyboard path needs its ring on the light bar. */
.mc-nav :slotted([aria-disabled="true"]),
.mc-nav :slotted(button:disabled) {
  opacity: 0.45;
  cursor: default;
}
.mc-nav :slotted(a:focus-visible),
.mc-nav :slotted(button:focus-visible) {
  outline: 3px solid var(--c-focus);
  outline-offset: -3px;
}
</style>
