<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- The one "there is nothing here" block for every portal.

     A screenshot audit found three shapes for one state: two bare sentences with no
     icon and no action, beside an error state that had both. A user who meets a lone
     line of grey text cannot tell whether the screen is empty, still loading, or
     broken — and has nothing to do next.

     Shape: an icon (slot, so each portal passes its own mapped glyph), a title, an
     optional hint, and an optional action slot. Nothing is required but the title, so
     the simplest call stays one line, and the colours come from the shared tokens. -->
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
  gap: 8px;
  padding: 28px 16px;
  text-align: center;
}
.apex-empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--c-surface-2, rgba(127, 127, 127, 0.12));
  color: var(--c-muted, #7d8f84);
}
.apex-empty-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--c-ink, inherit);
}
.apex-empty-hint {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--c-muted, #7d8f84);
}
.apex-empty-action {
  margin-top: 4px;
}
</style>
