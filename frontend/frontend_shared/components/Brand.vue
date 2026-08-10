<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <img :src="src" :width="size" :height="size" :alt="alt" :aria-hidden="alt ? undefined : 'true'" />
</template>

<script setup>
import { computed } from "vue";

import appIcon from "../assets/logo/apex-app-icon.svg";
import lockupAr from "../assets/logo/apex-lockup-ar.svg";
import lockupEn from "../assets/logo/apex-lockup-en.svg";
import markMono from "../assets/logo/apex-mark-mono.svg";
import markReverse from "../assets/logo/apex-mark-reverse.svg";
import mark from "../assets/logo/apex-mark.svg";

const SOURCES = {
  mark,
  reverse: markReverse,
  mono: markMono,
  "lockup-ar": lockupAr,
  "lockup-en": lockupEn,
  "app-icon": appIcon,
};

const props = defineProps({
  variant: { type: String, default: "mark" },
  size: { type: [Number, String], default: 28 },
  alt: { type: String, default: "" },
});

const src = computed(() => SOURCES[props.variant] || SOURCES.mark);
</script>
