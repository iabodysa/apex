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
.housing-app {
  display: flex;
  min-height: 100vh;
  width: 100%;
  flex-direction: column;
  background: var(--c-canvas);
}

/* Clears the fixed bar, plus the iOS home indicator the wrapper opts into with
   viewport-fit=cover. Without it the last row of a list is unreachable. */
.housing-view {
  flex: 1;
  padding-bottom: calc(64px + env(safe-area-inset-bottom));
}

.tabbar {
  position: fixed;
  inset-block-end: 0;
  inset-inline: 0;
  z-index: 50;
  display: flex;
  margin-inline: auto;
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
