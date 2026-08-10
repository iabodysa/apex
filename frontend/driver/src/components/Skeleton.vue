<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-3" aria-hidden="true">
    <div v-for="i in rows" :key="i" class="card card-pad skel-row">
      <div class="skel-line skel-w-60"></div>
      <div class="skel-line skel-w-40 mt-2"></div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Number, default: 3 },
});
</script>

<style scoped>
.skel-line {
  height: 12px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-ink) 9%, transparent);
  animation: skel-shimmer 1.4s ease infinite;
}
.skel-w-60 {
  width: 60%;
}
.skel-w-40 {
  width: 40%;
}
@keyframes skel-shimmer {
  50% { opacity: 0.54; }
}
@media (prefers-reduced-motion: reduce) {
  .skel-line {
    animation: none;
  }
}
</style>
