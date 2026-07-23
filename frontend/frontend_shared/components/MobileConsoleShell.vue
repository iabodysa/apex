<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- =====================================================================
     ARCHETYPE 2 — Mobile console (phone: driver + worker/مسار).
     One-hand ergonomics: a sticky dark header (greeting + actions + optional
     progress band), a single scrolling column of stacked cards, and a sticky
     bottom nav with 3–5 items at ≥52px tap targets and iOS safe-area padding.
     Matches the approved reference (screen 2).

     Consumes ONLY shared --c-* tokens. RTL-first (logical properties).

     SLOTS
       header   — full header content. Or use `title`/`subtitle` props for the
                  default greeting; slot overrides it.
       header-actions — end of the header row (bell, avatar). Ignored if the
                  `header` slot is provided.
       progress — optional band under the header (progress bar, day summary).
       default  — the scrolling content column (portal drops stacked cards).
       nav      — bottom-nav items (3–5). Any element works: each direct child
                  is auto-sized to an equal-width ≥52px tap target. Add class
                  `is-active` to the current item to tint it with the brand.

     PROPS
       title / subtitle — default header greeting text.
       maxWidth — column width on tablet+ (default 520px, one-hand column).
     ===================================================================== -->
<template>
  <div class="mc-shell" :style="{ maxWidth: cssWidth }">
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
  maxWidth: { type: [Number, String], default: 520 },
});

const cssWidth = computed(() =>
  typeof props.maxWidth === "number" ? props.maxWidth + "px" : props.maxWidth,
);
</script>

<style scoped>
.mc-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
  margin: 0 auto;
  width: 100%;
  background: var(--c-surface);
  color: var(--c-ink);
  font-family: var(--font);
  font-weight: var(--fw-body);
}

/* ---- sticky header ---- */
.mc-head {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--c-header-bg);
  color: var(--c-header-ink);
  padding: 14px 20px 16px;
}
.mc-head-row {
  display: flex;
  align-items: center;
  gap: 10px;
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
  gap: 8px;
}
.mc-progress {
  margin-top: 14px;
  background: color-mix(in srgb, #fff 8%, transparent);
  border-radius: var(--radius);
  padding: 12px 14px;
}

/* ---- scroll column ---- */
.mc-scroll {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 13px;
}

/* ---- bottom nav ---- */
.mc-nav {
  position: sticky;
  bottom: 0;
  z-index: 20;
  display: flex;
  gap: 4px;
  background: var(--c-surface-2);
  border-top: var(--border-width) solid var(--c-border);
  padding: 8px 6px calc(8px + env(safe-area-inset-bottom, 0px));
}
/* Each nav item becomes an equal-width ≥52px tap target, whatever element it is. */
.mc-nav :slotted(*) {
  flex: 1;
  min-height: 52px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  text-decoration: none;
  color: var(--c-muted);
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  border: none;
  background: none;
  border-radius: var(--radius);
  cursor: pointer;
}
.mc-nav :slotted(.is-active),
.mc-nav :slotted([aria-current="page"]) {
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 12%, transparent);
}
</style>
