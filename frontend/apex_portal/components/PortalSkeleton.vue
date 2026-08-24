<script setup>
import { __ } from "../core/i18n.js";

defineProps({
  rows: { type: Number, default: 3 },
  label: { type: String, default: () => __("Loading the data") },
});
</script>

<template>
  <div class="portal-skeleton" role="status" :aria-label="label">
    <span class="sr-only">{{ label }}</span>
    <div class="portal-skeleton__visual" aria-hidden="true">
      <article v-for="row in rows" :key="row" class="portal-skeleton__row">
        <span />
        <span />
        <span />
      </article>
    </div>
  </div>
</template>
