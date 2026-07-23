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
  bell,
  briefcase,
  calendar2,
  chevron,
  dashboard,
  download,
  external,
  fuel2,
  gauge,
  globe,
  help,
  home2,
  layers,
  phone2,
  pin,
  qr,
  refresh,
  route,
  shield,
  truck,
  user,
  x,
} from "@shared/components/icons.js";

// This portal's icon name -> shared geometry. Names unchanged, so no call site moves.
const ICONS = {
  "alert": alert,
  "badge": badge,
  "bell": bell,
  "briefcase": briefcase,
  "calendar": calendar2,
  "chevron": chevron,
  "dashboard": dashboard,
  "download": download,
  "external": external,
  "fuel": fuel2,
  "gauge": gauge,
  "globe": globe,
  "help": help,
  "home": home2,
  "layers": layers,
  "map-pin": pin,
  "phone": phone2,
  "qr": qr,
  "refresh": refresh,
  "route": route,
  "shield": shield,
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
