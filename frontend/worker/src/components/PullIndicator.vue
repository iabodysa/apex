<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div
    v-if="distance > 0 || refreshing"
    class="ptr"
    :style="indicatorStyle"
    aria-hidden="true"
  >
    <div class="spinner ptr-spinner" :class="{ 'ptr-paused': !refreshing }" :style="spinnerStyle"></div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  distance: { type: Number, default: 0 },
  refreshing: { type: Boolean, default: false },
  threshold: { type: Number, default: 70 },
});

const offset = computed(() => (props.refreshing ? 44 : Math.min(props.distance, 70) + 4));

const ratio = computed(() =>
  props.refreshing ? 1 : Math.min(props.distance / props.threshold, 1),
);

const indicatorStyle = computed(() => ({
  transform: `translateY(${offset.value}px)`,
  transition: props.refreshing ? "transform 0.2s ease" : "transform 0.18s ease",
}));

const spinnerStyle = computed(() => ({
  opacity: ratio.value,
  transform: `scale(${0.7 + ratio.value * 0.3})`,
}));
</script>

<style scoped>
.ptr {
  position: fixed;
  inset-block-start: 0;
  inset-inline: 0;
  z-index: 30;
  display: flex;
  justify-content: center;
  margin-block-start: -8px;
  pointer-events: none;
}
.ptr-spinner {
  height: 28px;
  width: 28px;
  border-width: 3px;
}
.ptr-paused {
  animation: none;
}
@media (prefers-reduced-motion: reduce) {
  .ptr-spinner {
    animation: none;
  }
}
</style>
