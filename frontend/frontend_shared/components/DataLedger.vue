<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="data-ledger">
    <div class="data-ledger-scroll">
      <table :aria-label="label">
        <thead v-if="$slots.head"><slot name="head" /></thead>
        <tbody><slot /></tbody>
      </table>
    </div>
    <div v-if="$slots.footer" class="data-ledger-footer"><slot name="footer" /></div>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
});
</script>

<style scoped>
.data-ledger {
  min-inline-size: 0;
  border-block: 1px solid var(--c-border-strong);
}
.data-ledger-scroll {
  min-inline-size: 0;
  overflow-x: auto;
}
table {
  inline-size: 100%;
  border-collapse: collapse;
  background: var(--c-surface);
  color: var(--c-ink);
  font-family: var(--font-brand);
  font-size: var(--fs-sm);
}
:deep(th),
:deep(td) {
  padding: var(--sp-3) var(--sp-4);
  border-block-end: 1px solid var(--c-border);
  text-align: start;
  vertical-align: middle;
}
:deep(th) {
  color: var(--c-muted);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  white-space: nowrap;
}
:deep(tbody tr:last-child td) {
  border-block-end: 0;
}
.data-ledger-footer {
  padding: var(--sp-3) var(--sp-4);
  border-block-start: 1px solid var(--c-border);
  background: var(--c-surface);
  color: var(--c-muted);
  font-size: var(--fs-sm);
}
</style>
