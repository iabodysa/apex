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
  calendar,
  car,
  chevron,
  clipboardList,
  fuel,
  gauge,
  rotateCw,
  triangleAlert,
} from "@shared/components/icons.js";

const ICONS = {
  calendar,
  car,
  chevron,
  "clipboard-list": clipboardList,
  fuel,
  gauge,
  "rotate-cw": rotateCw,
  "triangle-alert": triangleAlert,
};

const MIRROR = ["chevron"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
