<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="panel">
    <header class="panel-head">
      <h2 class="panel-title">{{ title }}</h2>
      <slot name="status" />
    </header>
    <div class="panel-body">
      <slot />
    </div>
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
});
</script>

<style scoped>
.panel {
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  padding: var(--sp-4);
}
.panel-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-height: var(--sp-5);
}
.panel-title {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
  letter-spacing: 0.02em;
}
.panel-body {
  margin-top: var(--sp-3);
}
</style>
