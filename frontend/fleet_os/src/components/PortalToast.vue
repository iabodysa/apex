<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <!-- frappe-ui 0.1.278 exports `toast` but not the surface that draws it, so the board keeps
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
.portal-toast {
  position: fixed;
  inset-block-end: var(--sp-5);
  inset-inline: var(--sp-4);
  inline-size: fit-content;
  margin-inline: auto;
  transform: translateY(var(--sp-4));
  max-width: min(90vw, 520px);
  padding: 10px 18px;
  border-radius: var(--radius);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  text-align: center;
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border-strong);
  box-shadow: var(--shadow);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.3s ease, transform 0.3s ease;
  z-index: 500;
}
.portal-toast.show {
  opacity: 1;
  transform: translateY(0);
}
.toast-green {
  color: var(--c-success);
  background: var(--c-success-bg);
  border-color: color-mix(in srgb, var(--c-success) 25%, transparent);
}
.toast-amber {
  color: var(--c-warning);
  background: var(--c-warning-bg);
  border-color: color-mix(in srgb, var(--c-warning) 25%, transparent);
}
.toast-red {
  color: var(--c-danger);
  background: var(--c-danger-bg);
  border-color: color-mix(in srgb, var(--c-danger) 25%, transparent);
}
</style>
