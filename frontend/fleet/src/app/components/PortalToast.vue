<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <!-- frappe-ui 0.1.278 exports `toast` but not the surface that draws it, so the portal keeps
       its own. The live region is always in the DOM: a region that appears at the same moment
       as its text is not announced. -->
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
/* Physical `left` with the transform on purpose: a transformed element does not flip with the
   writing direction, so pairing it with `inset-inline-start` pushed the toast off-canvas in
   RTL and needed a direction-specific patch to look centred. */
.portal-toast {
  position: fixed;
  inset-block-end: var(--sp-5);
  left: 50%;
  transform: translate(-50%, var(--sp-4));
  max-width: min(90vw, 460px);
  padding: 11px 18px;
  border-radius: var(--radius);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  text-align: center;
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border-strong);
  box-shadow: var(--shadow-lg);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.3s ease, transform 0.3s ease;
  z-index: 500;
}
.portal-toast.show {
  opacity: 1;
  transform: translate(-50%, 0);
}
.toast-green {
  color: var(--c-success);
  border-color: color-mix(in srgb, var(--c-success) 30%, transparent);
}
.toast-amber {
  color: var(--c-warning);
  border-color: color-mix(in srgb, var(--c-warning) 30%, transparent);
}
.toast-red {
  color: var(--c-danger);
  border-color: color-mix(in srgb, var(--c-danger) 30%, transparent);
}
</style>
