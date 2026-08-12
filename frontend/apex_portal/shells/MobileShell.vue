<script setup>
import { FeatherIcon } from "frappe-ui";
import { ar } from "../i18n/ar.js";

defineProps({
  title: { type: String, required: true },
  navigation: { type: Array, default: () => [] },
});
</script>

<template>
  <div class="mobile-shell">
    <a class="skip-link" href="#portal-content">{{ ar.skipToContent }}</a>
    <header class="mobile-shell__header">
      <h1 class="mobile-shell__title">{{ title }}</h1>
      <div class="mobile-shell__actions"><slot name="actions" /></div>
    </header>
    <main id="portal-content" class="mobile-shell__main" tabindex="-1">
      <slot />
    </main>
    <nav v-if="navigation.length" class="mobile-shell__nav" :aria-label="ar.primaryNavigation">
      <RouterLink
        v-for="item in navigation"
        :key="item.to"
        v-slot="{ href, navigate, isActive }"
        :to="item.to"
        custom
      >
        <a
          class="portal-nav-link"
          :href="href"
          :aria-current="isActive ? 'page' : undefined"
          @click="navigate"
        >
          <FeatherIcon v-if="item.icon" class="portal-nav-icon" :name="item.icon" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </a>
      </RouterLink>
    </nav>
  </div>
</template>
