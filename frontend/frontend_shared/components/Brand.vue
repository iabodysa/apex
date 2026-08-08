<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <svg
    v-if="mode === 'mark'"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <path d="M12 21c0-6 3-10 8-12-1 6-4 9-8 12Z" :fill="primaryColor" />
    <path d="M12 21C12 13 8 8 3 6c1 7 5 11 9 15Z" :fill="accentColor" opacity=".92" />
  </svg>

  <svg
    v-else
    viewBox="0 0 200 200"
    fill="none"
    preserveAspectRatio="xMidYMid meet"
    aria-hidden="true"
  >
    <path
      d="M70 10 A95 95 0 0 1 70 190"
      stroke="currentColor"
      stroke-width="26"
      stroke-linecap="round"
      fill="none"
    />
    <path
      d="M120 35 A70 70 0 0 1 120 165"
      stroke="currentColor"
      stroke-width="26"
      stroke-linecap="round"
      fill="none"
      opacity="0.6"
    />
  </svg>
</template>

<script setup>
/* The mark's two leaves are filled, not stroked, so `strokeWidth` no longer reaches it; it is
   kept because `arc` mode still draws strokes and both modes share one prop list. The default
   colours are the approved pair, which is read against the dark header the portals ship. */
defineProps({
  mode: { type: String, default: "mark" },
  size: { type: [Number, String], default: 28 },
  strokeWidth: { type: [Number, String], default: 6 },
  primaryColor: { type: String, default: "#60d297" },
  accentColor: { type: String, default: "#ffffff" },
});
</script>
