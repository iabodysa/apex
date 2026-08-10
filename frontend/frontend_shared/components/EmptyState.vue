<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="apex-empty" role="status">
    <div v-if="$slots.icon" class="apex-empty-icon">
      <slot name="icon" />
    </div>
    <p class="apex-empty-title">{{ title }}</p>
    <p v-if="hint" class="apex-empty-hint">{{ hint }}</p>
    <div v-if="$slots.action" class="apex-empty-action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  hint: { type: String, default: "" },
});
</script>

<style scoped>
.apex-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-2);
  padding: calc(var(--sp-6) + var(--sp-1)) var(--sp-4);
  text-align: center;
}
.apex-empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--tap-min);
  height: var(--tap-min);
  border-radius: var(--radius-pill);
  background: var(--c-surface-2, #ffffff);
  color: var(--c-muted, #47584f);
}
.apex-empty-title {
  margin: 0;
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink, inherit);
}
.apex-empty-hint {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: 1.7;
  color: var(--c-muted, #47584f);
}
.apex-empty-action {
  margin-top: var(--sp-1);
}
</style>
