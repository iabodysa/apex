<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <aside class="evidence-rail" :aria-label="label || title">
    <header v-if="title || eyebrow" class="evidence-rail-head">
      <p v-if="eyebrow">{{ eyebrow }}</p>
      <h2 v-if="title">{{ title }}</h2>
    </header>
    <div class="evidence-rail-body"><slot /></div>
  </aside>
</template>

<script setup>
defineProps({
  title: { type: String, default: "" },
  eyebrow: { type: String, default: "" },
  label: { type: String, default: "" },
});
</script>

<style scoped>
.evidence-rail {
  min-inline-size: 0;
  padding-inline-start: var(--sp-4);
  border-inline-start: 1px solid var(--c-border-strong);
}
.evidence-rail-head {
  padding-block-end: var(--sp-3);
  border-block-end: 1px solid var(--c-border);
}
.evidence-rail-head p {
  margin: 0 0 var(--sp-1);
  color: var(--c-accent-ink);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  text-transform: uppercase;
}
.evidence-rail h2 {
  margin: 0;
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
}
.evidence-rail-body {
  padding-block: var(--sp-4);
  color: var(--c-ink-soft);
  font-size: var(--fs-sm);
}
@media (max-width: 75.99rem) {
  .evidence-rail {
    padding-inline-start: 0;
    padding-block-start: var(--sp-4);
    border-inline-start: 0;
    border-block-start: 1px solid var(--c-border-strong);
  }
}
</style>
