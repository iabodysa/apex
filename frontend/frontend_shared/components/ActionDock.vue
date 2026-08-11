<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <footer class="action-dock">
    <div v-if="$slots.danger" class="action-dock-danger"><slot name="danger" /></div>
    <div v-if="$slots.secondary" class="action-dock-secondary"><slot name="secondary" /></div>
    <div v-if="$slots.primary" class="action-dock-primary"><slot name="primary" /></div>
  </footer>
</template>

<style scoped>
.action-dock {
  position: sticky;
  z-index: 10;
  inset-block-end: 0;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-block-start: var(--sp-5);
  padding: var(--sp-3);
  padding-block-end: calc(var(--sp-3) + env(safe-area-inset-bottom, 0px));
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--c-surface) 94%, transparent);
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
}
.action-dock-primary,
.action-dock-secondary,
.action-dock-danger {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.action-dock-primary {
  margin-inline-start: auto;
}
.action-dock :slotted(button) {
  min-block-size: var(--tap-min);
}
@media (max-width: 30rem) {
  .action-dock {
    align-items: stretch;
    flex-direction: column;
  }
  .action-dock-primary,
  .action-dock-secondary,
  .action-dock-danger {
    inline-size: 100%;
    margin-inline-start: 0;
  }
  .action-dock :slotted(button) {
    flex: 1;
    min-block-size: var(--tap-lg);
  }
}
</style>
