<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <article class="decision-stage">
    <header v-if="title || eyebrow || subtitle || $slots.actions" class="decision-stage-head">
      <div class="decision-stage-copy">
        <p v-if="eyebrow" class="decision-stage-eyebrow">{{ eyebrow }}</p>
        <h2 v-if="title">{{ title }}</h2>
        <p v-if="subtitle" class="decision-stage-subtitle">{{ subtitle }}</p>
      </div>
      <span v-if="$slots.actions" class="decision-stage-actions"><slot name="actions" /></span>
    </header>
    <div class="decision-stage-body"><slot /></div>
    <footer v-if="$slots.footer" class="decision-stage-footer"><slot name="footer" /></footer>
  </article>
</template>

<script setup>
defineProps({
  title: { type: String, default: "" },
  eyebrow: { type: String, default: "" },
  subtitle: { type: String, default: "" },
});
</script>

<style scoped>
.decision-stage {
  min-inline-size: 0;
  background: var(--c-surface);
  border-block-start: 4px solid var(--c-primary);
}
.decision-stage-head {
  display: flex;
  align-items: start;
  gap: var(--sp-4);
  padding: clamp(var(--sp-4), 3vw, var(--sp-6)) 0;
  border-block-end: 1px solid var(--c-border-strong);
}
.decision-stage-copy {
  min-inline-size: 0;
  flex: 1;
}
.decision-stage-eyebrow {
  margin: 0 0 var(--sp-1);
  color: var(--c-accent-ink);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  text-transform: uppercase;
}
.decision-stage h2 {
  margin: 0;
  color: var(--c-ink);
  font-size: var(--fs-h1);
  line-height: 1.2;
}
.decision-stage-subtitle {
  margin: var(--sp-2) 0 0;
  color: var(--c-ink-soft);
  font-family: var(--font-serif);
  line-height: 1.65;
}
.decision-stage-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
}
.decision-stage-body {
  min-inline-size: 0;
  padding-block: clamp(var(--sp-5), 4vw, var(--sp-8));
}
.decision-stage-footer {
  padding-block: var(--sp-4);
  border-block-start: 1px solid var(--c-border-strong);
}
</style>
