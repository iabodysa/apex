<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="card card-pad text-center">
    <div
      v-if="icon"
      class="avatar mx-auto mb-2 h-11 w-11"
      style="background: color-mix(in srgb, var(--c-mint) 25%, transparent); color: var(--c-primary)"
    >
      <Icon :name="icon" :size="22" />
    </div>
    <p v-if="title" class="font-semibold">{{ title }}</p>
    <p v-if="hint" class="text-sm text-muted">{{ hint }}</p>
  </div>
</template>

<script setup>
import Icon from "./Icon.vue";

defineProps({
  icon: { type: String, default: "" },
  title: { type: String, default: "" },
  hint: { type: String, default: "" },
});
</script>
