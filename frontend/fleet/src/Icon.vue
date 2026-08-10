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
  clipboardList,
  fuel,
  gauge,
  home,
  send,
} from "@shared/components/icons.js";

const ICONS = {
  calendar,
  "clipboard-list": clipboardList,
  fuel,
  gauge,
  home,
  send,
};

const MIRROR = ["send"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
  strokeWidth: { type: [Number, String], default: 1.75 },
});
</script>
