<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="ts-shell" :style="shellVars">
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
        <Button
          class="ts-menu"
          variant="ghost"
          size="xl"
          :label="menuLabel"
          :aria-label="menuLabel"
          aria-haspopup="true"
          :aria-expanded="drawerOpen ? 'true' : 'false'"
          @click="drawerOpen = !drawerOpen"
        >
          <template #icon>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
          </template>
        </Button>
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
import { Button } from "frappe-ui";
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

const MODAL_QUERY = "(max-width: 1023px)";
const narrow = ref(false);
if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
  const mq = window.matchMedia(MODAL_QUERY);
  narrow.value = mq.matches;
  const onChange = (e) => {
    narrow.value = e.matches;
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
  block-size: 100vh;
  block-size: 100dvh;
  min-inline-size: 0;
  overflow: hidden;
  background: var(--c-canvas);
  color: var(--c-ink);
  font-family: var(--font);
  font-weight: var(--fw-body);
}

.ts-nav {
  flex: 0 0 var(--ts-nav-w);
  width: var(--ts-nav-w);
  background: var(--c-header-bg);
  color: var(--c-header-ink);
  min-block-size: 0;
  overflow-y: auto;
  padding: var(--sp-5) var(--sp-4) calc(var(--sp-5) + env(safe-area-inset-bottom, 0px));
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ts-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: var(--sp-1) 6px 18px;
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
  min-block-size: var(--tap-min);
  padding: 10px var(--sp-3);
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
/* A tap leaves a touch device in :hover and it stays there, so the last button pressed keeps
   a highlight it has not earned. Guarded the way MobileConsoleShell already guards its own. */
@media (hover: hover) {
  .ts-nav-list :slotted(a:not(.is-active):hover),
  .ts-nav-list :slotted(button:not(.is-active):hover) {
    background: color-mix(in srgb, var(--c-header-ink) 8%, transparent);
    color: var(--c-header-ink);
  }
}
.ts-nav-list :slotted(a.is-active),
.ts-nav-list :slotted(a[aria-current="page"]),
.ts-nav-list :slotted(button.is-active) {
  background: color-mix(in srgb, var(--ts-accent) 22%, transparent);
  color: var(--c-header-ink);
  font-weight: var(--fw-heading);
}
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
  margin: 14px var(--sp-2) var(--sp-1);
}

.ts-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
  min-block-size: 0;
  background: var(--c-canvas);
}
.ts-top {
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: var(--sp-4) clamp(var(--sp-4), 3vw, var(--sp-6));
  overflow: hidden;
  border-block-end: var(--border-width) solid color-mix(in srgb, var(--c-header-ink) 14%, transparent);
  background: var(--c-header-bg);
  color: var(--c-header-ink);
}
.ts-top::after {
  content: "";
  position: absolute;
  z-index: -1;
  inset-block: -160%;
  inset-inline-end: clamp(4rem, 24vw, 24rem);
  inline-size: 1px;
  background: var(--c-header-accent);
  opacity: 0.3;
  transform: rotate(24deg);
}
.ts-menu {
  display: none;
  align-items: center;
  justify-content: center;
  min-inline-size: var(--tap-min);
  min-block-size: var(--tap-min);
  color: var(--c-header-ink);
  background: color-mix(in srgb, var(--c-header-ink) 10%, transparent);
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
  color: var(--c-header-ink);
}
.ts-sub {
  font-size: var(--fs-sm);
  color: color-mix(in srgb, var(--c-header-ink) 68%, transparent);
}
.ts-top-actions {
  margin-inline-start: auto;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.ts-scroll {
  flex: 1;
  min-inline-size: 0;
  min-block-size: 0;
  overflow-y: auto;
  overflow-x: clip;
  padding: 18px clamp(var(--sp-4), 3vw, var(--sp-6)) 28px;
}

.ts-kpis {
  display: flex;
  min-inline-size: 0;
  margin-block-end: var(--sp-5);
  overflow-x: auto;
  border-block: 1px solid var(--c-border-strong);
}
.ts-kpis :slotted(*) {
  flex: 1 0 min(12rem, 70vw);
  border-inline-end: 1px solid var(--c-border);
  border-radius: 0;
  box-shadow: none;
}

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
