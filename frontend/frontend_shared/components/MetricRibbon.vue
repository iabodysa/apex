<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <dl class="metric-ribbon">
    <div
      v-for="(metric, index) in metrics"
      :key="metric.key || metric.label || index"
      class="metric-ribbon-item"
      :data-tone="metric.tone || 'neutral'"
    >
      <dt>{{ metric.label }}</dt>
      <dd><bdi dir="auto">{{ metric.value }}</bdi></dd>
      <small v-if="metric.hint">{{ metric.hint }}</small>
    </div>
  </dl>
</template>

<script setup>
defineProps({
  metrics: { type: Array, default: () => [] },
});
</script>

<style scoped>
.metric-ribbon {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(8rem, 1fr);
  min-inline-size: 0;
  margin: 0;
  overflow-x: auto;
  border-block: 1px solid var(--c-border-strong);
  scrollbar-width: thin;
}
.metric-ribbon-item {
  position: relative;
  min-inline-size: 0;
  padding: var(--sp-4);
}
.metric-ribbon-item + .metric-ribbon-item {
  border-inline-start: 1px solid var(--c-border);
}
.metric-ribbon-item::before {
  content: "";
  position: absolute;
  inset-block-start: -1px;
  inset-inline: 0;
  block-size: 3px;
  background: var(--metric-accent, transparent);
}
.metric-ribbon-item[data-tone="success"] { --metric-accent: var(--c-success); }
.metric-ribbon-item[data-tone="warning"] { --metric-accent: var(--c-warning); }
.metric-ribbon-item[data-tone="danger"] { --metric-accent: var(--c-danger); }
.metric-ribbon-item[data-tone="info"] { --metric-accent: var(--c-info); }
.metric-ribbon dt,
.metric-ribbon small {
  color: var(--c-muted);
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
}
.metric-ribbon dd {
  margin: var(--sp-1) 0 0;
  color: var(--c-ink);
  font-size: clamp(1.4rem, 1vw + 1rem, 2rem);
  font-weight: var(--fw-heading);
  line-height: 1;
}
.metric-ribbon small {
  display: block;
  margin-block-start: var(--sp-2);
  font-weight: var(--fw-body);
}
</style>
