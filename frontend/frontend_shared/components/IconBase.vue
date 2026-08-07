<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    :class="{ 'apex-icon': align, 'apex-icon-mirror': doMirror }"
  >
    <template v-for="(c, i) in shape" :key="i">
      <path v-if="c.tag === 'path'" v-bind="c.attrs" />
      <circle v-else-if="c.tag === 'circle'" v-bind="c.attrs" />
      <rect v-else-if="c.tag === 'rect'" v-bind="c.attrs" />
      <line v-else-if="c.tag === 'line'" v-bind="c.attrs" />
      <polyline v-else-if="c.tag === 'polyline'" v-bind="c.attrs" />
      <polygon v-else-if="c.tag === 'polygon'" v-bind="c.attrs" />
    </template>
  </svg>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  shape: { type: Array, default: () => [] },
  name: { type: String, default: "" },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
  align: { type: Boolean, default: false },
  mirror: { type: Array, default: () => [] },
});

const doMirror = computed(() => props.mirror.includes(props.name));
</script>

<style scoped>
.apex-icon {
  display: inline-block;
  vertical-align: -0.18em;
  flex-shrink: 0;
}
:global([dir="rtl"] .apex-icon-mirror) {
  transform: scaleX(-1);
}
</style>
