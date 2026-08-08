<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <img :src="src" :width="size" :height="size" :alt="alt" :aria-hidden="alt ? undefined : 'true'" />
</template>

<script setup>
/* The approved marks are SVG masters, so this component chooses one and never redraws it.
   Path data lives in the files under assets/logo/ — copies of docs/brand/assets/logo/ and
   byte-identical to them — because a mark redrawn inside a component is a second master that
   drifts. Each variant already carries its own fills, which is why nothing here recolours.

   `mark` reads on light surfaces, `reverse` on forest and dark, `mono` for one-colour output
   such as print or a stamp. The lockups pair the mark with the wordmark and are the only
   correct choice beside a product name; the Arabic one stores its wordmark as outlines, so it
   must never be rebuilt from a runtime font. */
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
  /* Empty by default: a mark sitting beside the product name is decoration, and naming it
     twice makes a screen reader say it twice. Pass a label only when the mark stands alone. */
  alt: { type: String, default: "" },
});

const src = computed(() => SOURCES[props.variant] || SOURCES.mark);
</script>
