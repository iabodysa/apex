<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Thin per-portal icon wrapper. The SVG geometry lives once in
     @shared/components/icons.js; this file just maps the names THIS portal uses to
     their geometry and hands them to the shared IconBase renderer. Importing only
     the names used keeps the built bundle to this portal's icon subset. Preserves
     this portal's original baseline alignment and RTL mirror set. -->
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
import {
  arrowLeft,
  building,
  calendar,
  chartColumn,
  check,
  chevron,
  circleCheck,
  circleDashed,
  circleDot,
  clipboardCheck,
  flag,
  layoutGrid,
  loader,
  mail,
  pencil,
  search,
  send2,
  settings,
  shield,
  shield2,
  shieldAlert,
  sparkles,
  triangleAlert,
  x,
} from "@shared/components/icons.js";

// This portal's icon name -> shared geometry. Names unchanged, so no call site moves.
const ICONS = {
  "arrow-left": arrowLeft,
  "building": building,
  "calendar": calendar,
  "chart-column": chartColumn,
  "check": check,
  "check-circle": circleCheck,
  "chevron": chevron,
  "circle-dashed": circleDashed,
  "circle-dot": circleDot,
  "clipboard-check": clipboardCheck,
  "flag": flag,
  "layout-grid": layoutGrid,
  "loader": loader,
  "mail": mail,
  "pencil": pencil,
  "search": search,
  "send": send2,
  "settings": settings,
  "shield": shield2,
  "shield-alert": shieldAlert,
  "shield-check": shield,
  "sparkles": sparkles,
  "triangle-alert": triangleAlert,
  "x": x,
};

// Directional glyphs mirrored under [dir="rtl"] (unchanged from this portal's original).
const MIRROR = ["chevron","arrow-left"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
