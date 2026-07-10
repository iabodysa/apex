<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Shared inline-SVG icon renderer. Takes a `shape` (the ordered child-element
     list from @shared/components/icons.js) and draws it inside the one standard
     lucide-style <svg> wrapper (viewBox 24, currentColor stroke, round caps).
     Every portal's Icon.vue is a thin map over this, so the svg boilerplate, the
     baseline-alignment class, and the RTL mirror rule live in exactly one place.

       align   — apply the inline-block/baseline-nudge class (portals that had the
                 old `.fp-icon`/`.sp-icon` class pass true; the others pass false so
                 their icon box is unchanged).
       mirror  — icon names that flip horizontally under [dir="rtl"] (directional
                 glyphs like chevron / arrow-left). Empty for portals that never
                 mirrored, so behaviour is preserved exactly. -->
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
  // Ordered child-element list: [{ tag, attrs }, ...] from icons.js. Missing (an
  // unknown name) renders an empty svg — the same blank the old per-name v-if gave.
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
/* Inline icons sit on the text baseline; nudge so they read as part of the label.
   Only applied when the portal opts in via `align` (its original had this class). */
.apex-icon {
  display: inline-block;
  vertical-align: -0.18em;
  flex-shrink: 0;
}
/* Directional glyphs point "forward"; in RTL forward is leftward, so mirror. Keep
   the whole selector inside ONE :global() so the class survives minification — a
   split :global([dir=rtl]) .class collapses to a bare [dir=rtl] rule that flips ALL
   content. */
:global([dir="rtl"] .apex-icon-mirror) {
  transform: scaleX(-1);
}
</style>
