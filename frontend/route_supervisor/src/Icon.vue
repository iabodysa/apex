<!-- Copyright (c) 2026, afmcoltd -->
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
  badge,
  building,
  bus,
  check,
  chevron,
  circleCheck,
  clipboardCheck,
  clock,
  pin,
  refresh,
  route,
  triangleAlert,
  truck,
  user,
  x,
} from "@shared/components/icons.js";

const ICONS = {
  badge,
  building,
  bus,
  check,
  chevron,
  "circle-check": circleCheck,
  "clipboard-check": clipboardCheck,
  clock,
  pin,
  refresh,
  route,
  "triangle-alert": triangleAlert,
  truck,
  user,
  x,
};

const MIRROR = ["chevron"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
  strokeWidth: { type: [Number, String], default: 1.75 },
});
</script>
