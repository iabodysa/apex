<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- =====================================================================
     ARCHETYPE 3 — Tablet supervisor console (safety / housing / route).
     A denser command surface: a dark side nav (brand + grouped links), a top
     bar (page title + search/actions), a KPI-tile row, and a main content
     region the portal fills with a live table / map / approval panel. Matches
     the approved reference (screen 3).

     One shared style for all three supervisor domains; differentiate only by a
     subtle per-domain accent — pass `accent` (any color / token) to tint the
     active nav item, the brand, and focus states without forking the layout.

     Consumes ONLY shared --c-* tokens. RTL-first. Responsive: the side nav is
     fixed at ≥1024px (--bp-desktop) and collapses to a slide-in drawer with a
     menu button below that — the shell owns the drawer state, portals just fill
     the `nav` slot.

     SLOTS
       brand   — top of the side nav (mark + wordmark).
       nav     — side-nav links/groups (portal supplies <a>/<button>, section
                 labels via class `nav-label`). Add `is-active` to the current.
       title-actions — end of the top bar (search, avatar, filters).
       kpis    — KPI tiles. The shell wraps them in a responsive auto-fit grid;
                 the portal supplies the tiles. Omit to hide the row.
       default — main content (table, map, approvals…).

     PROPS
       title / subtitle — top-bar heading text (slot `title-actions` for the end).
       accent  — per-domain accent color/token (default: --c-primary).
       navWidth — side-nav width at desktop (default 220px).
     ===================================================================== -->
<template>
  <div class="ts-shell" :style="shellVars">
    <!-- scrim behind the drawer on narrow widths -->
    <div v-if="drawerOpen" class="ts-scrim" @click="drawerOpen = false"></div>

    <aside
      ref="navEl"
      class="ts-nav"
      :class="{ 'ts-nav-open': drawerOpen }"
      :role="drawerIsModal ? 'dialog' : null"
      :aria-modal="drawerIsModal ? 'true' : null"
      :aria-label="drawerIsModal ? menuLabel : null"
    >
      <div class="ts-brand"><slot name="brand" /></div>
      <nav class="ts-nav-list" @click="drawerOpen = false"><slot name="nav" /></nav>
    </aside>

    <div class="ts-main">
      <header class="ts-top">
        <button
          type="button"
          class="ts-menu"
          :aria-label="menuLabel"
          aria-haspopup="true"
          :aria-expanded="drawerOpen ? 'true' : 'false'"
          @click="drawerOpen = !drawerOpen"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <div class="ts-title">
          <h1>{{ title }}</h1>
          <div v-if="subtitle" class="ts-sub">{{ subtitle }}</div>
        </div>
        <span class="ts-top-actions"><slot name="title-actions" /></span>
      </header>

      <div class="ts-scroll">
        <div v-if="$slots.kpis" class="ts-kpis"><slot name="kpis" /></div>
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onScopeDispose } from "vue";
import { useOverlay } from "../useOverlay.js";

const props = defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  accent: { type: String, default: "var(--c-primary)" },
  navWidth: { type: [Number, String], default: 220 },
  menuLabel: { type: String, default: "Menu" },
});

const drawerOpen = ref(false);
const navEl = ref(null);

// Below --bp-desktop the side nav is a slide-in drawer over a scrim, i.e. a modal
// surface; at or above it the same element is a static sidebar that must stay in the
// normal tab order. The same 1023px the stylesheet switches on decides which, so the
// two can never disagree. matchMedia is absent under jsdom (component tests), where
// the drawer is simply never modal.
const MODAL_QUERY = "(max-width: 1023px)";
const narrow = ref(false);
if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
  const mq = window.matchMedia(MODAL_QUERY);
  narrow.value = mq.matches;
  const onChange = (e) => {
    narrow.value = e.matches;
    // Widening past the breakpoint turns the drawer back into a plain sidebar; leaving
    // `drawerOpen` set would keep the scrim state around with nothing rendering it.
    if (!e.matches) drawerOpen.value = false;
  };
  mq.addEventListener("change", onChange);
  onScopeDispose(() => mq.removeEventListener("change", onChange));
}

const drawerIsModal = computed(() => drawerOpen.value && narrow.value);

useOverlay({
  active: drawerIsModal,
  container: navEl,
  close: () => (drawerOpen.value = false),
});

const shellVars = computed(() => ({
  "--ts-accent": props.accent,
  "--ts-nav-w": typeof props.navWidth === "number" ? props.navWidth + "px" : props.navWidth,
}));
</script>

<style scoped>
.ts-shell {
  display: flex;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--c-surface);
  color: var(--c-ink);
  font-family: var(--font);
  font-weight: var(--fw-body);
}

/* ---- side nav ---- */
.ts-nav {
  flex: 0 0 var(--ts-nav-w);
  width: var(--ts-nav-w);
  background: var(--c-header-bg);
  color: var(--c-header-ink);
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ts-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 6px 18px;
  font-weight: var(--fw-heading);
}
.ts-nav-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ts-nav-list :slotted(a),
.ts-nav-list :slotted(button) {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  text-decoration: none;
  color: color-mix(in srgb, var(--c-header-ink) 80%, transparent);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  border: none;
  background: none;
  width: 100%;
  cursor: pointer;
  text-align: start;
}
.ts-nav-list :slotted(a:hover),
.ts-nav-list :slotted(button:hover) {
  background: color-mix(in srgb, var(--c-header-ink) 8%, transparent);
  color: var(--c-header-ink);
}
.ts-nav-list :slotted(a.is-active),
.ts-nav-list :slotted(a[aria-current="page"]),
.ts-nav-list :slotted(button.is-active) {
  background: color-mix(in srgb, var(--ts-accent) 22%, transparent);
  color: var(--c-header-ink);
  font-weight: var(--fw-heading);
}
/* Disabled and focus are two of the eight mandatory component states; a nav item
   that cannot act until a record is selected must say so rather than silently
   no-op, and the keyboard path needs a visible ring on the dark ground. */
.ts-nav-list :slotted(a[aria-disabled="true"]),
.ts-nav-list :slotted(button:disabled) {
  opacity: 0.45;
  cursor: default;
  background: none;
}
.ts-nav-list :slotted(a:focus-visible),
.ts-nav-list :slotted(button:focus-visible) {
  outline: 2px solid var(--c-header-accent, var(--c-focus));
  outline-offset: 2px;
}
.ts-nav-list :slotted(.nav-label) {
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  letter-spacing: 0.1em;
  opacity: 0.5;
  margin: 14px 8px 4px;
}

/* ---- main ---- */
.ts-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--c-surface);
}
.ts-top {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px clamp(16px, 3vw, 24px);
  border-bottom: var(--border-width) solid var(--c-border);
}
.ts-menu {
  display: none;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--radius-sm);
  border: var(--border-width) solid var(--c-border);
  background: var(--c-surface-2);
  color: var(--c-ink);
  cursor: pointer;
  flex: 0 0 auto;
}
.ts-menu:focus-visible {
  outline: 2px solid var(--c-focus);
  outline-offset: 2px;
}
.ts-title h1 {
  margin: 0;
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  letter-spacing: -0.01em;
}
.ts-sub {
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.ts-top-actions {
  margin-inline-start: auto;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.ts-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 18px clamp(16px, 3vw, 24px) 28px;
}

/* ---- KPI row: responsive auto-fit tile grid ---- */
.ts-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 13px;
  margin-bottom: 18px;
}

/* ---- responsive: below --bp-desktop (1024px) the side nav is a drawer ---- */
.ts-scrim {
  display: none;
}
@media (max-width: 1023px) {
  .ts-menu {
    display: inline-flex;
  }
  .ts-nav {
    position: fixed;
    inset-block: 0;
    inset-inline-start: 0;
    z-index: 40;
    transform: translateX(-100%);
    transition: transform 0.22s ease;
    box-shadow: var(--shadow-lg);
  }
  [dir="rtl"] .ts-nav {
    transform: translateX(100%);
  }
  .ts-nav.ts-nav-open {
    transform: translateX(0);
  }
  .ts-scrim {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 30;
    background: var(--c-scrim);
  }
}
@media (prefers-reduced-motion: reduce) {
  .ts-nav {
    transition: none;
  }
}
</style>
