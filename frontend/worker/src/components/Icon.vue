<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Thin per-portal icon wrapper. The SVG geometry lives once in
     @shared/components/icons.js; this file just maps the names THIS portal uses to
     their geometry and hands them to the shared IconBase renderer. Importing only
     the names used keeps the built bundle to this portal's icon subset. Preserves
     this portal's original baseline alignment (none) and RTL mirror set. -->
<template>
  <IconBase
    :shape="ICONS[name]"
    :name="name"
    :size="size"
    :stroke-width="strokeWidth"
    :align="false"
    :mirror="MIRROR"
  />
</template>

<script setup>
import IconBase from "@shared/components/IconBase.vue";
import {
  alert,
  badge,
  bed,
  briefcase,
  building2,
  bus,
  calendar2,
  card,
  check,
  chevron,
  clock,
  dashboard,
  doc,
  external,
  fuel2,
  globe,
  help,
  home2,
  image,
  layers,
  message,
  phone2,
  pin2,
  plus,
  refresh2,
  route,
  send,
  truck,
  user,
  x,
} from "@shared/components/icons.js";

// This portal's icon name -> shared geometry. Names unchanged, so no call site moves.
const ICONS = {
  "alert": alert,
  "badge": badge,
  "bed": bed,
  "briefcase": briefcase,
  "building": building2,
  "bus": bus,
  "calendar": calendar2,
  "card": card,
  "check": check,
  "chevron": chevron,
  "clock": clock,
  "dashboard": dashboard,
  "doc": doc,
  "external": external,
  "fuel": fuel2,
  "globe": globe,
  "help": help,
  "home": home2,
  "image": image,
  "layers": layers,
  "message": message,
  "phone": phone2,
  "pin": pin2,
  "plus": plus,
  "refresh": refresh2,
  "route": route,
  "send": send,
  "truck": truck,
  "user": user,
  "x": x,
};

// Directional glyphs mirrored under [dir="rtl"] (unchanged from this portal's original).
const MIRROR = [];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
