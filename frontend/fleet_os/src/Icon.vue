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
  shieldAlert,
  triangleAlert,
  user,
  wrench,
  x,
} from "@shared/components/icons.js";

const ICONS = {
  banknote,
  bell,
  bike,
  building,
  calendar,
  car,
  "chart-column": chartColumn,
  chevron,
  "circle-check": circleCheck,
  "circle-dot": circleDot,
  "circle-pause": circlePause,
  "clipboard-list": clipboardList,
  crash,
  fuel,
  funnel,
  hammer,
  "id-card": idCard,
  key,
  "layout-grid": layoutGrid,
  list,
  lock,
  "lock-open": lockOpen,
  package: packageGlyph,
  phone,
  pin,
  "rotate-cw": rotateCw,
  search,
  "shield-alert": shieldAlert,
  "triangle-alert": triangleAlert,
  user,
  wrench,
  x,
};

const MIRROR = ["chevron"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
  strokeWidth: { type: [Number, String], default: 1.75 },
});
</script>
