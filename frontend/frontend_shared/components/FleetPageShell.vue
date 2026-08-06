<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- =====================================================================
     ARCHETYPE 1 — Employee page (fleet).
     A calm, roomy single-purpose web page: a dark forest top bar (brand +
     nav + actions), a greeting band, then a centered content column the
     portal fills with cards/forms. Density is deliberately low — an employee
     opens this once a fortnight to perform one action.

     Consumes ONLY shared --c-* tokens (see @shared/tokens.css) — no color is
     hard-coded — so it recolours with light/dark and stays on-brand. RTL-first:
     all edges use logical properties, so it mirrors under <html dir="rtl">.

     THE TOP NAV BELOW --bp-tablet IS THE SHELL'S ANSWER, NOT THE PORTAL'S.
     It used to be `display: none`, which is only correct for a portal that has
     somewhere else to put its destinations. Fleet has no router and no second
     nav, so it was overriding the shell with a three-part selector to win the
     specificity fight and put the row back. One archetype cannot have two
     answers to one question: the nav now wraps onto its own full-width scrolling
     row inside the sticky bar, and a portal that genuinely wants it gone hides
     its own slot content.

     SLOTS
       brand    — brand mark + wordmark on the header (start side).
       nav      — top nav links (e.g. <a>Home</a> …).
       actions  — header end side (avatar, lang/theme toggles).
       heading  — greeting band. Or use the `title`/`subtitle` props for the
                  default markup; the slot fully overrides it.
       default  — page content. The portal drops its own grid/cards here; the
                  shell only provides the centered max-width column + padding.
       footer   — optional full-width note under the content.

     PROPS
       title    — big greeting line (used only if `heading` slot is empty).
       subtitle — muted line under the greeting.
       maxWidth — content column width (default 1180px).
     ===================================================================== -->
<template>
  <div class="fleet-shell">
    <header class="fleet-top">
      <span class="fleet-brand"><slot name="brand" /></span>
      <nav class="fleet-nav"><slot name="nav" /></nav>
      <span class="fleet-actions"><slot name="actions" /></span>
    </header>

    <main class="fleet-body" :style="{ maxWidth: cssWidth }">
      <div v-if="$slots.heading || title" class="fleet-heading">
        <slot name="heading">
          <h1 class="fleet-hello">{{ title }}</h1>
          <p v-if="subtitle" class="fleet-sub">{{ subtitle }}</p>
        </slot>
      </div>

      <slot />

      <footer v-if="$slots.footer" class="fleet-footer"><slot name="footer" /></footer>
    </main>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  maxWidth: { type: [Number, String], default: 1180 },
});

const cssWidth = computed(() =>
  typeof props.maxWidth === "number" ? props.maxWidth + "px" : props.maxWidth,
);
</script>

<style scoped>
.fleet-shell {
  min-height: 100vh;
  min-height: 100dvh;
  background:
    radial-gradient(1200px 600px at 80% -10%, color-mix(in srgb, var(--c-mint) 14%, transparent), transparent 60%),
    radial-gradient(1000px 500px at 10% 0%, color-mix(in srgb, var(--c-primary) 10%, transparent), transparent 55%),
    var(--c-canvas);
  background-attachment: fixed;
  color: var(--c-ink);
  font-family: var(--font);
  font-weight: var(--fw-body);
}

/* ---- top bar ---- */
.fleet-top {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: 14px clamp(var(--sp-4), 4vw, var(--sp-8));
  background: var(--c-header-bg);
  color: var(--c-header-ink);
}
.fleet-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-weight: var(--fw-heading);
}
.fleet-nav {
  margin-inline-start: auto;
  display: flex;
  align-items: center;
  gap: var(--sp-1);
}
.fleet-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
}
/* If there is no nav, the actions cluster takes the auto margin instead. */
.fleet-nav:empty + .fleet-actions {
  margin-inline-start: auto;
}

/* Portal nav links inherit these without extra markup. --tap-min, not padding
   alone: at --fs-sm the padded box lands near 31px, and this same row is what a
   phone gets after the wrap below. */
.fleet-nav :slotted(a) {
  display: inline-flex;
  align-items: center;
  min-height: var(--tap-min);
  font-size: var(--fs-sm);
  color: color-mix(in srgb, var(--c-header-ink) 78%, transparent);
  text-decoration: none;
  padding: 7px var(--sp-3);
  border-radius: var(--radius-sm);
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}
.fleet-nav :slotted(a:hover) {
  background: color-mix(in srgb, var(--c-header-ink) 10%, transparent);
  color: var(--c-header-ink);
}
.fleet-nav :slotted(a.is-active),
.fleet-nav :slotted(a[aria-current="page"]) {
  background: color-mix(in srgb, var(--c-header-accent) 20%, transparent);
  color: var(--c-header-ink);
  font-weight: var(--fw-semibold);
}
/* Two of the eight mandatory states. The ring is the header accent because the
   shared --c-focus is tuned against the page ground, not against forest chrome. */
.fleet-nav :slotted(a[aria-disabled="true"]) {
  opacity: 0.45;
  cursor: default;
  background: none;
}
.fleet-nav :slotted(a:focus-visible) {
  outline: 3px solid var(--c-header-accent);
  outline-offset: 2px;
}

/* ---- body ---- */
.fleet-body {
  margin: 0 auto;
  padding: clamp(var(--sp-5), 4vw, 34px) clamp(var(--sp-4), 4vw, var(--sp-8)) 80px;
}
.fleet-heading {
  margin-bottom: 22px;
}
.fleet-hello {
  margin: 0 0 3px;
  font-size: clamp(20px, 3vw, 26px);
  font-weight: var(--fw-heading);
  letter-spacing: -0.01em;
  text-wrap: balance;
}
.fleet-sub {
  margin: 0;
  color: var(--c-muted);
  font-size: var(--fs-sm);
}
.fleet-footer {
  margin-top: 48px;
  padding: 22px var(--sp-6);
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

/* 767px = --bp-tablet (frontend_shared/tokens.css) minus 1; keep in sync — CSS
   @media conditions cannot read a custom property. Below the tablet width the
   nav wraps to its own full-width row under brand + actions and scrolls inline
   rather than squeezing the brand out of the bar. `order` moves the row without
   touching slot order, so the DOM sequence a screen reader follows is unchanged. */
@media (max-width: 767px) {
  .fleet-top {
    flex-wrap: wrap;
    row-gap: var(--sp-2);
  }
  .fleet-nav {
    order: 3;
    flex-basis: 100%;
    margin-inline-start: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .fleet-nav::-webkit-scrollbar {
    display: none;
  }
  .fleet-actions {
    margin-inline-start: auto;
  }
}
</style>
