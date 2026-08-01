<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Housing shell: the two routed screens (Count, Delivery) plus the bottom bar
     that switches between them. Chrome only — neither screen's content lives
     here. -->
<template>
  <div class="housing-app">
    <div class="housing-view">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>

    <!-- Two destinations, so the bar splits in half. It is width-capped and
         centred on the same column as .app-shell: a viewport-wide bar under a
         720px column reads as a different page's furniture. -->
    <nav class="tabbar" :aria-label="t('nav.sections')">
      <router-link to="/count" class="tabbar-item" active-class="tabbar-item-on">
        <Icon name="clipboard-check" :size="20" />
        <span class="tabbar-label">{{ t("nav.count") }}</span>
      </router-link>
      <router-link to="/delivery" class="tabbar-item" active-class="tabbar-item-on">
        <Icon name="package" :size="20" />
        <span class="tabbar-label">{{ t("nav.delivery") }}</span>
      </router-link>
    </nav>
  </div>
</template>

<script setup>
import { watch } from "vue";
import { useI18n } from "./i18n";
import Icon from "./components/Icon.vue";

const { t, dir } = useI18n();

// The document's reading direction is a shell concern, not a screen's: written
// here it survives a route change, where a per-page watcher left /delivery
// rendering LTR whenever it was the entry route.
watch(
  dir,
  (d) => {
    document.documentElement.setAttribute("dir", d);
    document.documentElement.setAttribute("lang", d === "rtl" ? "ar" : "en");
  },
  { immediate: true },
);
</script>

<style>
/* height, not min-height: a flex container left at height:auto still sizes to its
   content, so the scroll column below would grow past the viewport and the bar
   would go back to floating over the list. dvh first so an iOS toolbar sliding in
   does not crop the bar; vh is the fallback for browsers without dvh. */
.housing-app {
  display: flex;
  height: 100vh;
  height: 100dvh;
  width: 100%;
  flex-direction: column;
  background: var(--c-canvas);
}

/* The scroll column, so the bar below can hold layout space instead of floating
   over it. `overflow-y:auto` is what makes this work: it resolves this flex
   item's automatic minimum size to 0, so the shell stays viewport-height and the
   list scrolls INSIDE this box. Same construction as the shared
   MobileConsoleShell. */
.housing-view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  /* Reaching the end of the column must not start dragging the page behind it. */
  overscroll-behavior: contain;
}

/* Sticky, NOT fixed. A fixed bar is outside flow, so it covers whatever sits at
   the viewport bottom at every scroll offset — on a short viewport that was the
   first card's stepper, whose taps went to the nav link underneath. A padding
   reserve on the scroll column cannot fix that: it only frees the document's
   LAST row. As a flex sibling of the scroll column the bar occupies real space,
   so no content is ever behind it. */
.tabbar {
  position: sticky;
  inset-block-end: 0;
  z-index: 50;
  display: flex;
  margin-inline: auto;
  width: 100%;
  max-width: var(--shell-max, 480px);
  background: var(--c-surface-2);
  border-top: 1px solid var(--c-border);
  padding-bottom: env(safe-area-inset-bottom);
  box-shadow: var(--shadow-sm);
}

/* --tap-lg: a standing supervisor taps this one-handed. */
.tabbar-item {
  flex: 1;
  min-height: var(--tap-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 8px 4px;
  color: var(--c-muted);
  text-decoration: none;
  transition: color 0.15s ease;
}
.tabbar-item-on {
  color: var(--c-primary);
  font-weight: var(--fw-heading);
}
.tabbar-label {
  font-size: var(--fs-2xs);
  font-weight: var(--fw-semibold);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* 768px = shared --bp-tablet (frontend_shared/tokens.css); keep in sync —
   CSS @media conditions cannot read a custom property. */
@media (min-width: 768px) {
  .tabbar {
    --shell-max: 720px;
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
