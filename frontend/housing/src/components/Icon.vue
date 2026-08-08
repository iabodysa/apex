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
  alert,
  arrowLeft,
  bed,
  box,
  building,
  calendar,
  check,
  chevron,
  circleCheck,
  clipboardCheck,
  doc,
  door,
  flag,
  idCard,
  image,
  key,
  layers,
  loader,
  mail,
  minus,
  packageGlyph2,
  pencil,
  phone,
  plus,
  qr,
  refresh,
  route,
  scale,
  search,
  send2,
  shield,
  triangleAlert,
  truck,
  user,
  x,
} from "@shared/components/icons.js";

const ICONS = {
  "alert": alert,
  "arrow-left": arrowLeft,
  "bed": bed,
  "box": box,
  "building": building,
  "calendar": calendar,
  "check": check,
  "check-circle": circleCheck,
  "chevron": chevron,
  "clipboard-check": clipboardCheck,
  "doc": doc,
  "door": door,
  "flag": flag,
  "id-card": idCard,
  "image": image,
  "key": key,
  "layers": layers,
  "loader": loader,
  "mail": mail,
  "minus": minus,
  "package": packageGlyph2,
  "pencil": pencil,
  "phone": phone,
  "plus": plus,
  "qr": qr,
  "refresh": refresh,
  "route": route,
  "scale": scale,
  "search": search,
  "send": send2,
  "shield": shield,
  "shield-check": shield,
  "triangle-alert": triangleAlert,
  "truck": truck,
  "user": user,
  "x": x,
};

const MIRROR = ["chevron", "arrow-left"];

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 22 },
  strokeWidth: { type: [Number, String], default: 2 },
});
</script>
