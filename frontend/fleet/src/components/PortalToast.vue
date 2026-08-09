<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div
    class="portal-toast"
    :class="[toast.show ? 'show' : '', 'toast-' + toast.type]"
    role="status"
    aria-live="polite"
    aria-atomic="true"
  >
    <span class="portal-toast-mark" aria-hidden="true"></span>
    <span>{{ toast.show ? toast.msg : "" }}</span>
  </div>
</template>

<script setup>
defineProps({
  toast: { type: Object, required: true },
});
</script>

<style scoped>
.portal-toast {
  position: fixed;
  inset-block-end: calc(5rem + env(safe-area-inset-bottom, 0px));
  left: 50%;
  z-index: 500;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  inline-size: max-content;
  max-inline-size: min(90vw, 32rem);
  min-block-size: var(--tap-min);
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius-sm);
  background: var(--c-header-bg);
  color: var(--c-header-ink);
  box-shadow: var(--shadow-lg);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  opacity: 0;
  pointer-events: none;
  transform: translate(-50%, var(--sp-4));
  transition: opacity 180ms ease, transform 180ms ease;
}
.portal-toast.show {
  opacity: 1;
  transform: translate(-50%, 0);
}
.portal-toast-mark {
  inline-size: 0.55rem;
  block-size: 1.5rem;
  flex: 0 0 auto;
  border-radius: var(--radius-pill);
  background: var(--c-header-accent);
}
.toast-amber .portal-toast-mark {
  background: var(--c-warning-fill);
}
.toast-red .portal-toast-mark {
  background: var(--c-danger);
}

@media (min-width: 56rem) {
  .portal-toast {
    inset-block-end: var(--sp-6);
  }
}

@media (prefers-reduced-motion: reduce) {
  .portal-toast {
    transition: none;
  }
}
</style>
