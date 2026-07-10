<template>
  <div class="h-screen w-full flex flex-col bg-gray-50">
    <!-- Router View loads the current page (Count or Delivery) -->
    <div class="flex-1 overflow-y-auto pb-16">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>

    <!-- Bottom Navigation Bar -->
    <nav class="fixed bottom-0 w-full bg-white border-t border-gray-200 flex shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)] z-50 h-16">
      <router-link
        to="/count"
        class="flex-1 flex flex-col items-center justify-center gap-1 text-gray-500 hover:text-gray-900 transition-colors"
        active-class="text-[var(--c-accent)] font-semibold"
      >
        <Icon name="clipboard-check" :size="20" />
        <span class="text-[10px] uppercase tracking-wider">{{ t("nav.count", "Inventory Count") }}</span>
      </router-link>
      
      <router-link
        to="/delivery"
        class="flex-1 flex flex-col items-center justify-center gap-1 text-gray-500 hover:text-gray-900 transition-colors"
        active-class="text-[var(--c-accent)] font-semibold"
      >
        <Icon name="package" :size="20" />
        <span class="text-[10px] uppercase tracking-wider">{{ t("nav.delivery", "Asset Delivery") }}</span>
      </router-link>
    </nav>
  </div>
</template>

<script setup>
import { useI18n } from "./i18n";
import Icon from "./components/Icon.vue";

const { t } = useI18n();
</script>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
