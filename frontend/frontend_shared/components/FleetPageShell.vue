<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- =====================================================================
     ARCHETYPE 1 — Fleet page (employee desktop / browser).
     A calm, roomy single-purpose web page: a dark forest top bar (brand +
     nav + actions), a greeting band, then a centered content column the
     portal fills with cards/forms. Matches the approved reference
     (scratch/portal-archetypes-preview.html, screen 1).

     Consumes ONLY shared --c-* tokens (see @shared/tokens.css) — no color is
     hard-coded — so it recolours with light/dark and stays on-brand. RTL-first:
     all edges use logical properties, so it mirrors under <html dir="rtl">.

     SLOTS
       brand    — brand mark + wordmark on the header (start side).
       nav      — top nav links (e.g. <a>Home</a> …). Hidden < tablet.
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
  gap: 12px;
  padding: 14px clamp(16px, 4vw, 32px);
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
  gap: 4px;
}
.fleet-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
/* If there is no nav, the actions cluster takes the auto margin instead. */
.fleet-nav:empty + .fleet-actions {
  margin-inline-start: auto;
}

/* Portal nav links inherit these without extra markup. */
.fleet-nav :slotted(a) {
  font-size: var(--fs-sm);
  color: color-mix(in srgb, var(--c-header-ink) 78%, transparent);
  text-decoration: none;
  padding: 7px 12px;
  border-radius: var(--radius-sm);
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

/* ---- body ---- */
.fleet-body {
  margin: 0 auto;
  padding: clamp(20px, 4vw, 34px) clamp(16px, 4vw, 32px) 80px;
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
  padding: 22px 24px;
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

@media (max-width: 767px) {
  /* 768px = --bp-tablet: collapse the top nav on narrow viewports. */
  .fleet-nav {
    display: none;
  }
  .fleet-actions {
    margin-inline-start: auto;
  }
}
</style>
