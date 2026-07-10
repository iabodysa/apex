<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Test-fixture stand-in for a portal's local Icon.vue (resolved via `@` in
     vitest.config), so BuildingPicker can mount without pulling a real icon set. -->
<template>
  <i class="icon-stub" :data-icon="name"></i>
</template>
<script setup>
defineProps({
  name: { type: String, default: "" },
  size: { type: [Number, String], default: 22 },
});
</script>
