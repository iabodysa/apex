<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="sk" role="status" :aria-label="label">
    <div class="sk-card">
      <div class="sk-head">
        <span class="sk-block sk-line sk-line-label"></span>
        <span class="sk-block sk-pill"></span>
      </div>
      <span class="sk-block sk-line sk-line-value"></span>
      <span class="sk-block sk-line sk-line-meta"></span>
    </div>

    <div class="sk-card">
      <span class="sk-block sk-line sk-line-label"></span>
      <div class="sk-facts">
        <span class="sk-block sk-line sk-line-fact"></span>
        <span class="sk-block sk-line sk-line-fact"></span>
        <span class="sk-block sk-line sk-line-fact"></span>
      </div>
    </div>

    <div class="sk-card">
      <span class="sk-block sk-line sk-line-label"></span>
      <div v-for="row in rows" :key="row" class="sk-row">
        <span class="sk-block sk-mark"></span>
        <span class="sk-lines">
          <span class="sk-block sk-line sk-line-title"></span>
          <span class="sk-block sk-line sk-line-meta"></span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Number, default: 3 },
  label: { type: String, required: true },
});
</script>

<style scoped>
/* The shape the content will take, so nothing moves after it is drawn
   (DESIGN.md §6). The shimmer itself is the global .sk-block rule in index.css,
   which carries no [dir=rtl] selector on purpose. */
.sk {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.sk-card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-4);
  border-radius: var(--radius);
  border: var(--border-width) solid var(--c-border);
  background: var(--c-surface-2);
}
.sk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}
.sk-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-5);
}
.sk-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-height: var(--tap-md);
}
.sk-lines {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.sk-mark {
  height: var(--sp-8);
  width: var(--sp-8);
  flex-shrink: 0;
  border-radius: var(--radius-sm);
}
.sk-line-label {
  width: 30%;
}
.sk-line-value {
  width: 62%;
  height: var(--sp-5);
}
.sk-line-title {
  width: 72%;
}
.sk-line-meta {
  width: 44%;
}
.sk-line-fact {
  width: var(--sp-8);
}
.sk-pill {
  height: var(--sp-5);
  width: calc(var(--sp-8) + var(--sp-4));
  flex-shrink: 0;
  border-radius: var(--radius-pill);
}
</style>
