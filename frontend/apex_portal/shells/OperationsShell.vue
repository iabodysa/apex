<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { FeatherIcon } from "frappe-ui";
import { ar } from "../i18n/ar.js";

const brandMark = "/assets/apex/icons/brand/apex-mark.svg";

const props = defineProps({
  title: { type: String, required: true },
  navigation: { type: Array, default: () => [] },
});
const isMobile = ref(globalThis.window?.innerWidth < 768);
function updateViewport() {
  isMobile.value = globalThis.window?.innerWidth < 768;
}
onMounted(() => globalThis.window?.addEventListener("resize", updateViewport));
onBeforeUnmount(() => globalThis.window?.removeEventListener("resize", updateViewport));

const mobileGroups = computed(() => {
  const groups = new Map();
  for (const item of props.navigation) {
    const name = item.group || "أخرى";
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(item);
  }
  return [...groups.entries()].map(([label, items]) => ({ label, items }));
});
</script>

<template>
  <div class="operations-shell">
    <a class="skip-link" href="#portal-content">{{ ar.skipToContent }}</a>
    <aside class="operations-shell__rail">
      <div class="operations-shell__brand">
        <img class="portal-brand-mark" :src="brandMark" alt="" />
        <span>{{ ar.brandName }}</span>
      </div>
      <nav v-if="navigation.length && !isMobile" class="operations-shell__nav" :aria-label="ar.primaryNavigation">
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
      <nav v-if="mobileGroups.length && isMobile" class="operations-shell__mobile-nav" :aria-label="ar.primaryNavigation">
        <details v-for="group in mobileGroups" :key="group.label" class="operations-shell__mobile-group">
          <summary>{{ group.label }}</summary>
          <RouterLink
            v-for="item in group.items"
            :key="item.to"
            class="portal-nav-link"
            :to="item.to"
          >
            <FeatherIcon v-if="item.icon" class="portal-nav-icon" :name="item.icon" aria-hidden="true" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </details>
      </nav>
    </aside>
    <div class="operations-shell__body">
      <header class="operations-shell__header">
        <h1 class="operations-shell__title">{{ title }}</h1>
        <div class="operations-shell__actions"><slot name="actions" /></div>
      </header>
      <main id="portal-content" class="operations-shell__main" tabindex="-1">
        <slot />
      </main>
    </div>
  </div>
</template>
