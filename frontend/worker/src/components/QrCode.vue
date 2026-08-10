<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <svg
    v-if="matrix"
    :viewBox="`0 0 ${dim} ${dim}`"
    :width="size"
    :height="size"
    role="img"
    :aria-label="label"
    shape-rendering="crispEdges"
    :style="{ display: 'block', background: colors.light, borderRadius: '8px' }"
  >
    <rect :width="dim" :height="dim" :fill="colors.light" />
    <path :d="path" :fill="colors.dark" />
  </svg>
</template>

<script setup>
import { computed } from "vue";
import { encodeQr } from "../utils/qrcode";
import { qrColors } from "../utils/qrColor";

const props = defineProps({
  value: { type: String, required: true },
  size: { type: Number, default: 220 },
  quiet: { type: Number, default: 4 },
  label: { type: String, required: true },
  themed: { type: Boolean, default: false },
  darkVar: { type: String, default: "--c-ink" },
  lightVar: { type: String, default: "--c-surface" },
});

const colors = computed(() => {
  if (!props.themed || typeof window === "undefined") return { dark: "#000000", light: "#ffffff" };
  const cs = getComputedStyle(document.documentElement);
  const inkColor = cs.getPropertyValue(props.darkVar).trim();
  const surfaceColor = cs.getPropertyValue(props.lightVar).trim();
  return qrColors(inkColor, surfaceColor);
});

const matrix = computed(() => {
  try {
    return encodeQr(props.value);
  } catch (e) {
    return null;
  }
});

const dim = computed(() => (matrix.value ? matrix.value.size + props.quiet * 2 : 0));

const path = computed(() => {
  if (!matrix.value) return "";
  const { size, modules } = matrix.value;
  const q = props.quiet;
  let d = "";
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if (modules[r][c]) d += `M${c + q} ${r + q}h1v1h-1z`;
    }
  }
  return d;
});
</script>
