<!-- Copyright (c) 2026, afmcoltd -->
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

const MIRROR = [];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
