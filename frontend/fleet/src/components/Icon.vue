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
  banknote,
  bell,
  bike,
  building,
  calendar,
  car,
  chartColumn,
  chevron,
  circleCheck,
  circleDot,
  circlePause,
  clipboardList,
  crash,
  fuel,
  funnel,
  hammer,
  home,
  idCard,
  key,
  layoutGrid,
  list,
  lock,
  lockOpen,
  packageGlyph,
  phone,
  pin,
  rotateCw,
  search,
  settings,
  shieldAlert,
  triangleAlert,
  user,
  wrench,
  x,
} from "@shared/components/icons.js";

// This portal's icon name -> shared geometry. Names unchanged, so no call site moves.
const ICONS = {
  "banknote": banknote,
  "bell": bell,
  "bike": bike,
  "building": building,
  "calendar": calendar,
  "car": car,
  "chart-column": chartColumn,
  "chevron": chevron,
  "circle-check": circleCheck,
  "circle-dot": circleDot,
  "circle-pause": circlePause,
  "clipboard-list": clipboardList,
  "crash": crash,
  "fuel": fuel,
  "funnel": funnel,
  "hammer": hammer,
  "home": home,
  "id-card": idCard,
  "key": key,
  "layout-grid": layoutGrid,
  "list": list,
  "lock": lock,
  "lock-open": lockOpen,
  "package": packageGlyph,
  "phone": phone,
  "pin": pin,
  "rotate-cw": rotateCw,
  "search": search,
  "settings": settings,
  "shield-alert": shieldAlert,
  "triangle-alert": triangleAlert,
  "user": user,
  "wrench": wrench,
  "x": x,
};

// Directional glyphs mirrored under [dir="rtl"] (unchanged from this portal's original).
const MIRROR = ["chevron"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
