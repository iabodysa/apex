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
  bed,
  briefcase,
  building2,
  bus,
  calendar2,
  card,
  check,
  circleCheck,
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
  "check-circle": circleCheck,
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

const MIRROR = [];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
