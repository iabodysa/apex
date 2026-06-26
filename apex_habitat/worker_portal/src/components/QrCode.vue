<!-- Renders a scannable QR for `value` as crisp SVG (no canvas blur at any size).
     Used for the worker's boarding pass; the encoder is dependency-free (qrcode.js). -->
<template>
  <svg
    v-if="matrix"
    :viewBox="`0 0 ${dim} ${dim}`"
    :width="size"
    :height="size"
    role="img"
    :aria-label="label"
    shape-rendering="crispEdges"
    style="display: block; background: #fff; border-radius: 8px"
  >
    <rect :width="dim" :height="dim" fill="#fff" />
    <path :d="path" fill="#000" />
  </svg>
</template>

<script setup>
import { computed } from "vue";
import { encodeQr } from "../qrcode";

const props = defineProps({
  value: { type: String, required: true },
  size: { type: Number, default: 220 },
  // Quiet zone in modules (the spec requires 4 for reliable scanning).
  quiet: { type: Number, default: 4 },
  label: { type: String, default: "QR code" },
});

// Encode once per value; a malformed/oversized payload yields null (the parent
// shows a fallback rather than a broken image).
const matrix = computed(() => {
  try {
    return encodeQr(props.value);
  } catch (e) {
    return null;
  }
});

const dim = computed(() => (matrix.value ? matrix.value.size + props.quiet * 2 : 0));

// One SVG <path> of all dark modules (far fewer DOM nodes than one <rect> each).
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
