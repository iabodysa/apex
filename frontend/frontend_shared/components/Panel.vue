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
  min-inline-size: 0;
  padding-block: var(--sp-4);
  border-block: var(--border-width) solid var(--c-border-strong);
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
  color: var(--c-ink);
}
.panel-body {
  margin-block-start: var(--sp-4);
}
</style>
