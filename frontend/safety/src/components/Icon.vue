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
  arrowLeft,
  building,
  calendar,
  check,
  chevron,
  circleCheck,
  circleDashed,
  clipboardCheck,
  flag,
  loader,
  mail,
  pencil,
  search,
  send2,
  shield,
  shield2,
  sparkles,
  triangleAlert,
  x,
} from "@shared/components/icons.js";

const ICONS = {
  "arrow-left": arrowLeft,
  "building": building,
  "calendar": calendar,
  "check": check,
  "check-circle": circleCheck,
  "chevron": chevron,
  "circle-dashed": circleDashed,
  "clipboard-check": clipboardCheck,
  "flag": flag,
  "loader": loader,
  "mail": mail,
  "pencil": pencil,
  "search": search,
  "send": send2,
  "shield": shield2,
  "shield-check": shield,
  "sparkles": sparkles,
  "triangle-alert": triangleAlert,
  "x": x,
};

const MIRROR = ["chevron","arrow-left"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
