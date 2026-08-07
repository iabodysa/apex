<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <IconBase :shape="ICONS[name]" :name="name" :size="size" :stroke-width="strokeWidth"
            :align="true" :mirror="MIRROR" />
</template>

<script setup>
import IconBase from "@shared/components/IconBase.vue";
import {
  route,
  bus,
  truck,
  check,
  circleCheck,
  circleDot,
  clipboardCheck,
  x,
  chevron,
  arrowLeft,
  user,
  building,
  pin,
  clock,
  gauge,
  flag,
  refresh,
  triangleAlert,
  calendar,
  badge,
  sparkles,
} from "@shared/components/icons.js";

const ICONS = {
  route,
  bus,
  truck,
  check,
  "circle-check": circleCheck,
  "circle-dot": circleDot,
  "clipboard-check": clipboardCheck,
  x,
  chevron,
  "arrow-left": arrowLeft,
  user,
  building,
  pin,
  clock,
  gauge,
  flag,
  refresh,
  "triangle-alert": triangleAlert,
  calendar,
  badge,
  sparkles,
};

const MIRROR = ["chevron", "arrow-left"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
