<!-- Copyright (c) 2026, AFMCO and contributors -->
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
  box,
  building,
  check,
  chevron,
  circleCheck,
  clipboardCheck,
  door,
  key,
  minus,
  packageGlyph2,
  plus,
  refresh,
  scale,
  search,
  send2,
  shield,
  triangleAlert,
  truck,
} from "@shared/components/icons.js";

const ICONS = {
  "box": box,
  "building": building,
  "check": check,
  "check-circle": circleCheck,
  "chevron": chevron,
  "clipboard-check": clipboardCheck,
  "door": door,
  "key": key,
  "minus": minus,
  "package": packageGlyph2,
  "plus": plus,
  "refresh": refresh,
  "scale": scale,
  "search": search,
  "send": send2,
  "shield-check": shield,
  "triangle-alert": triangleAlert,
  "truck": truck,
};

const MIRROR = ["chevron"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
