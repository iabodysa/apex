<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <!-- frappe-ui 0.1.278 exports `toast` but not the surface that draws it (`ToastProvider` /
       `Toasts` are absent from src/index.ts and a deep import is outside the package exports
       map), so the portal keeps its own. The live region is always in the DOM: a region that
       appears at the same moment as its text is not announced. -->
  <div class="portal-toast" :class="[toast.show ? 'show' : '', 'toast-' + toast.type]"
       role="status" aria-live="polite" aria-atomic="true">
    {{ toast.show ? toast.msg : "" }}
  </div>
</template>

<script setup>
defineProps({
  toast: { type: Object, required: true },
});
</script>

<style scoped>
/* Centring uses physical `left` with a transform on purpose: a transformed element does not
   flip with the writing direction, so pairing it with `inset-inline-start` pushed the toast
   off-canvas in RTL. */
.portal-toast {
  position: fixed;
  inset-block-end: var(--sp-6);
  left: 50%;
  transform: translate(-50%, var(--sp-5));
  max-width: min(90vw, 460px);
  padding: var(--sp-3) var(--sp-5);
  border-radius: var(--radius-pill);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  text-align: center;
  background: var(--c-ink);
  color: var(--c-canvas);
  box-shadow: var(--shadow-lg);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease, transform 0.2s ease;
  z-index: 80;
}
.portal-toast.show {
  opacity: 1;
  transform: translate(-50%, 0);
}
.toast-ok {
  background: var(--c-success);
  color: var(--c-primary-ink);
}
.toast-bad {
  background: var(--c-danger);
  color: var(--c-danger-ink);
}
</style>
