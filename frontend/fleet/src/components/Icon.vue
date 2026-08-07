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
import { car, chevron, clipboardList, fuel, rotateCw, triangleAlert } from "@shared/components/icons.js";

const ICONS = {
  "car": car,
  "chevron": chevron,
  "clipboard-list": clipboardList,
  "fuel": fuel,
  "rotate-cw": rotateCw,
  "triangle-alert": triangleAlert,
};

const MIRROR = ["chevron"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
