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
/* Sizes come from the scale, never from a literal (DESIGN.md §8): a hint set at 12.5px
   sat between --fs-sm and --fs-xs and belonged to neither, so the one empty state every
   portal shares was the only text on screen off the type scale. The vertical padding is
   the one deliberate exception — an empty block needs more air than --sp-6 and less than
   --sp-8, and it is written as a sum of scale steps rather than a new number. */
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
  background: var(--c-surface-2, rgba(127, 127, 127, 0.12));
  color: var(--c-muted, #7d8f84);
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
  color: var(--c-muted, #7d8f84);
}
.apex-empty-action {
  margin-top: var(--sp-1);
}
</style>
