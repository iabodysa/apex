<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Thin per-portal icon wrapper. The SVG geometry lives once in
     @shared/components/icons.js; this file just maps the names THIS portal uses to
     their geometry and hands them to the shared IconBase renderer. Importing only
     the names used keeps the built bundle to this portal's icon subset. Preserves
     this portal's original baseline alignment and RTL mirror set.

     [#a281] The map below is the EMPLOYEE page's subset (5 names, all in App.vue).
     It used to carry the supervisor board's 34 names — a stale leftover of the
     fleet -> fleet_os fork that shipped 26 unused icon geometries and made this
     file byte-identical to fleet_os's. That identity was the bug, not the design:
     the per-portal map is deliberate (it is what keeps each bundle to its own
     icons), so keep this list matched to actual usage. The three that dropped out
     (circle-dot / settings / circle-check) went with the local ThemeToggle when it
     was promoted to @shared/components/ThemeToggle.vue, which imports its own
     geometry directly. -->
<template>
  <IconBase
    :shape="ICONS[name]"
    :name="name"
    :size="size"
    :stroke-width="strokeWidth"
    :align="true"
    :mirror="MIRROR"
  />
</template>

<script setup>
import IconBase from "@shared/components/IconBase.vue";
import { car, chevron, clipboardList, fuel, rotateCw, triangleAlert } from "@shared/components/icons.js";

// This portal's icon name -> shared geometry. Names unchanged, so no call site moves.
const ICONS = {
  "car": car,
  "chevron": chevron,
  "clipboard-list": clipboardList,
  "fuel": fuel,
  "rotate-cw": rotateCw,
  "triangle-alert": triangleAlert,
};

// Directional glyphs mirrored under [dir="rtl"] (unchanged from this portal's original).
const MIRROR = ["chevron"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
