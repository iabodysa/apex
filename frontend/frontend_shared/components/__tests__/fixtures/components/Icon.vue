<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <i class="icon-stub" :data-icon="name"></i>
</template>
<script setup>
defineProps({
  name: { type: String, default: "" },
  size: { type: [Number, String], default: 22 },
});
</script>
