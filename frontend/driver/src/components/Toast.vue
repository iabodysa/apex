<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="toast-host" aria-live="polite" aria-atomic="true">
    <transition-group name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="toast"
        :class="toast.kind === 'err' ? 'toast-err' : 'toast-ok'"
        role="status"
        @click="dismissToast(toast.id)"
      >
        <Icon :name="toast.kind === 'err' ? 'alert' : 'badge'" :size="18" class="shrink-0" />
        <span>{{ toast.message }}</span>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import Icon from "./Icon.vue";
import { toasts, dismissToast } from "../toast";
</script>

<style scoped>
.toast-host {
  position: fixed;
  inset-inline: 0;
  bottom: calc(72px + env(safe-area-inset-bottom));
  z-index: 40;
  margin: 0 auto;
  max-width: 480px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 10px 16px;
  border-radius: var(--radius-pill);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  box-shadow: var(--shadow-lg);
}
.toast-ok {
  background: var(--c-success);
  color: var(--c-primary-ink);
}
.toast-err {
  background: var(--c-danger);
  color: var(--c-danger-ink);
}
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
