<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <nav class="domain-nav" :aria-label="t('nav.housingHelp')">
    <router-link
      v-for="item in items"
      :key="item.to"
      :to="item.to"
      :aria-current="item.routes.includes(route.name) ? 'page' : undefined"
    >
      <Icon :name="item.icon" :size="18" />
      <span>{{ t(item.labelKey) }}</span>
    </router-link>
  </nav>
</template>

<script setup>
import { useRoute } from "vue-router";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();
const route = useRoute();
const items = [
  { to: "/accommodation", routes: ["accommodation"], icon: "building", labelKey: "nav.accommodation" },
  { to: "/custody", routes: ["custody"], icon: "briefcase", labelKey: "nav.custody" },
  { to: "/requests", routes: ["requests", "request-detail"], icon: "message", labelKey: "nav.requests" },
];
</script>

<style scoped>
.domain-nav {
  display: flex;
  gap: var(--sp-2);
  overflow-x: auto;
  padding-block-end: var(--sp-3);
  border-block-end: 1px solid var(--c-border-strong);
  scrollbar-width: thin;
}
.domain-nav a {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  min-block-size: var(--tap-min);
  padding-inline: var(--sp-3);
  border-radius: var(--radius-sm);
  color: var(--c-muted);
  font-weight: var(--fw-semibold);
  text-decoration: none;
  white-space: nowrap;
}
.domain-nav a[aria-current="page"] {
  background: color-mix(in srgb, var(--c-mint) 20%, transparent);
  color: var(--c-primary);
}
</style>
