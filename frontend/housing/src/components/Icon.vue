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
  box,
  building,
  check,
  chevron,
  circleCheck,
  clipboardCheck,
  door,
  filter,
  loader,
  mail,
  minus,
  packageGlyph2,
  plus,
  scale,
  search,
  send2,
  triangleAlert,
  x,
} from "@shared/components/icons.js";

// This portal's icon name -> shared geometry. Names unchanged, so no call site moves.
const ICONS = {
  "arrow-left": arrowLeft,
  "box": box,
  "building": building,
  "check": check,
  "check-circle": circleCheck,
  "chevron": chevron,
  "clipboard-check": clipboardCheck,
  "door": door,
  "filter": filter,
  "loader": loader,
  "mail": mail,
  "minus": minus,
  "package": packageGlyph2,
  "plus": plus,
  "scale": scale,
  "search": search,
  "send": send2,
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
