<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Renders a scannable QR for `value` as crisp SVG (no canvas blur at any size).
     Used for the worker's boarding pass; the encoder is dependency-free (qrcode.js).
     Colors follow the active theme (via qrColor.js) but are contrast-clamped so the
     code always stays scannable — verified by a round-trip jsQR decode test. -->
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
import { computed, ref, onMounted, onUnmounted } from "vue";
import { encodeQr } from "../utils/qrcode";
import { qrColors } from "../utils/qrColor";

const props = defineProps({
  value: { type: String, required: true },
  size: { type: Number, default: 220 },
  // Quiet zone in modules (the spec requires 4 for reliable scanning).
  quiet: { type: Number, default: 4 },
  label: { type: String, default: "QR code" },
  // When true, recolor the dark modules + light bg to the active theme (clamped
  // for scannability). When false, plain black-on-white (the safe default).
  themed: { type: Boolean, default: false },
  // CSS custom-property names to read the theme's dark/light source colors from.
  darkVar: { type: String, default: "--c-ink" },
  lightVar: { type: String, default: "--c-surface" },
});

// Re-resolve the theme colors when the theme attribute or language (RTL) flips.
// A MutationObserver on <html data-theme/dir> is the honest trigger: themes are
// applied by a server-set attribute, not a Vue ref this component owns.
const themeTick = ref(0);
let observer = null;
onMounted(() => {
  if (typeof MutationObserver === "undefined") return;
  observer = new MutationObserver(() => themeTick.value++);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme", "class"],
  });
});
onUnmounted(() => observer && observer.disconnect());

// Resolve {dark, light} from the active theme's computed CSS vars, contrast-clamped.
// Non-themed (or SSR/no-DOM) renders fall back to plain black-on-white.
const colors = computed(() => {
  themeTick.value; // dependency: recompute when the theme attribute mutates
  if (!props.themed || typeof window === "undefined") return { dark: "#000000", light: "#ffffff" };
  const cs = getComputedStyle(document.documentElement);
  const inkColor = cs.getPropertyValue(props.darkVar).trim();
  const surfaceColor = cs.getPropertyValue(props.lightVar).trim();
  return qrColors(inkColor, surfaceColor);
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
