<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="work-queue" :aria-label="label || title">
    <header v-if="title || eyebrow || $slots.actions" class="work-queue-head">
      <div>
        <p v-if="eyebrow" class="work-queue-eyebrow">{{ eyebrow }}</p>
        <h2 v-if="title">{{ title }}</h2>
      </div>
      <span v-if="$slots.actions" class="work-queue-actions"><slot name="actions" /></span>
    </header>
    <div class="work-queue-list"><slot /></div>
    <footer v-if="$slots.footer" class="work-queue-footer"><slot name="footer" /></footer>
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, default: "" },
  eyebrow: { type: String, default: "" },
  label: { type: String, default: "" },
});
</script>

<style scoped>
.work-queue {
  min-inline-size: 0;
  border-block: 1px solid var(--c-border-strong);
  background: color-mix(in srgb, var(--c-surface) 88%, transparent);
}
.work-queue-head {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: var(--sp-3);
  padding: var(--sp-4) 0;
  border-block-end: 1px solid var(--c-border);
}
.work-queue-head > div {
  min-inline-size: 0;
  flex: 1;
}
.work-queue-eyebrow {
  margin: 0 0 var(--sp-1);
  color: var(--c-accent-ink);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  text-transform: uppercase;
}
.work-queue h2 {
  margin: 0;
  color: var(--c-ink);
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
}
.work-queue-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
}
.work-queue-list {
  min-inline-size: 0;
}
.work-queue-list :slotted(*) {
  border-block-end: 1px solid var(--c-border);
}
.work-queue-list :slotted(*:last-child) {
  border-block-end: 0;
}
.work-queue-footer {
  padding-block: var(--sp-3);
  border-block-start: 1px solid var(--c-border);
  color: var(--c-muted);
  font-size: var(--fs-sm);
}
</style>
