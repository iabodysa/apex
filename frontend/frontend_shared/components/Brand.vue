<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <svg
    v-if="mode === 'mark'"
    :width="size"
    :height="size"
    viewBox="0 0 48 48"
    fill="none"
    aria-hidden="true"
  >
    <path
      d="M19 6 A18 18 0 0 0 19 42"
      :stroke="primaryColor"
      :stroke-width="strokeWidth"
      stroke-linecap="round"
      fill="none"
    />
    <path
      d="M29 6 A18 18 0 0 1 29 42"
      :stroke="accentColor"
      :stroke-width="strokeWidth"
      stroke-linecap="round"
      fill="none"
    />
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
defineProps({
  mode: { type: String, default: "mark" },
  size: { type: [Number, String], default: 28 },
  strokeWidth: { type: [Number, String], default: 6 },
  primaryColor: { type: String, default: "var(--c-header-accent)" },
  accentColor: { type: String, default: "var(--c-header-accent)" },
});
</script>
