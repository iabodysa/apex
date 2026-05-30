<!-- AFMCO brand assets, rendered inline so they recolour with the active theme
     tokens (currentColor) and stay crisp at any size. Two parts:

       <Brand mode="mark">     the standalone split-circle emblem — two thick
                               facing semicircular arcs ( ) around a core gap.
       <Brand mode="arc">      a single large arc used as the header
                               supergraphic (decorative framing element).

     The mark mirrors the AFMCO logo symbol from Brand.md (the "split circle").
     Flat 2D, no gradients, no shadows — honouring the "Flatten" philosophy. -->
<template>
  <!-- Standalone emblem: two facing arcs forming an implied, split circle. -->
  <svg
    v-if="mode === 'mark'"
    :width="size"
    :height="size"
    viewBox="0 0 48 48"
    fill="none"
    aria-hidden="true"
  >
    <!-- Left arc (primary) -->
    <path
      d="M19 6 A18 18 0 0 0 19 42"
      :stroke="primaryColor"
      :stroke-width="strokeWidth"
      stroke-linecap="round"
      fill="none"
    />
    <!-- Right arc (accent) -->
    <path
      d="M29 6 A18 18 0 0 1 29 42"
      :stroke="accentColor"
      :stroke-width="strokeWidth"
      stroke-linecap="round"
      fill="none"
    />
  </svg>

  <!-- Header supergraphic: one large arc, low-contrast, framing the right edge. -->
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
  // "mark" = standalone emblem, "arc" = header supergraphic.
  mode: { type: String, default: "mark" },
  size: { type: [Number, String], default: 28 },
  strokeWidth: { type: [Number, String], default: 6 },
  // Colours default to the brand tokens; overridable for on-dark headers.
  primaryColor: { type: String, default: "var(--c-header-accent)" },
  accentColor: { type: String, default: "var(--c-header-accent)" },
});
</script>
