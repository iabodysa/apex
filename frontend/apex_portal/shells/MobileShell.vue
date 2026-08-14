<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { ar } from "../i18n/ar.js";
import PortalPushPrompt from "../components/PortalPushPrompt.vue";

const reverseBrandMark = "/assets/apex/icons/brand/apex-mark-reverse.svg";
const primaryLimit = 4;

const props = defineProps({
  title: { type: String, required: true },
  navigation: { type: Array, default: () => [] },
});

const route = useRoute();
const hasOverflow = computed(() => props.navigation.length > primaryLimit + 1);
const primaryNavigation = computed(() => (
  hasOverflow.value ? props.navigation.slice(0, primaryLimit) : props.navigation
));
const overflowNavigation = computed(() => (
  hasOverflow.value ? props.navigation.slice(primaryLimit) : []
));
const overflowActive = computed(() => (
  overflowNavigation.value.some((item) => item.to === route.path)
));
</script>

<template>
  <div class="mobile-shell">
    <a class="skip-link" href="#portal-content">{{ ar.skipToContent }}</a>
    <header class="mobile-shell__header">
      <div class="portal-brand-lockup">
        <img class="portal-brand-mark" :src="reverseBrandMark" alt="" />
        <h1 class="mobile-shell__title">{{ title }}</h1>
      </div>
      <div class="mobile-shell__actions"><slot name="actions" /></div>
    </header>
    <main id="portal-content" class="mobile-shell__main" tabindex="-1">
      <PortalPushPrompt />
      <slot />
    </main>
    <nav v-if="navigation.length" class="mobile-shell__nav" :aria-label="ar.primaryNavigation">
      <RouterLink
        v-for="item in primaryNavigation"
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
          <span v-if="item.icon" class="portal-nav-icon" :class="item.icon" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </a>
      </RouterLink>
      <details v-if="overflowNavigation.length" class="mobile-shell__more">
        <summary class="portal-nav-link" :aria-current="overflowActive ? 'page' : undefined">
          <span class="portal-nav-icon lucide-more-horizontal" aria-hidden="true" />
          <span>المزيد</span>
        </summary>
        <div class="mobile-shell__more-menu">
          <RouterLink
            v-for="item in overflowNavigation"
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
              <span v-if="item.icon" class="portal-nav-icon" :class="item.icon" aria-hidden="true" />
              <span>{{ item.label }}</span>
            </a>
          </RouterLink>
        </div>
      </details>
    </nav>
  </div>
</template>
