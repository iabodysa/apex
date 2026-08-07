<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="mc-shell" :style="shellVars">
    <header class="mc-head">
      <slot name="header">
        <div class="mc-head-row">
          <div class="mc-greet">
            <small v-if="subtitle">{{ subtitle }}</small>
            <b>{{ title }}</b>
          </div>
          <span class="mc-head-actions"><slot name="header-actions" /></span>
        </div>
      </slot>
      <div v-if="$slots.progress" class="mc-progress"><slot name="progress" /></div>
    </header>

    <main class="mc-scroll"><slot /></main>

    <nav v-if="$slots.nav" class="mc-nav"><slot name="nav" /></nav>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  maxWidth: { type: [Number, String], default: 480 },
});

const shellVars = computed(() => ({
  "--mc-width": typeof props.maxWidth === "number" ? props.maxWidth + "px" : props.maxWidth,
}));
</script>

<style scoped>
.mc-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  margin: 0 auto;
  width: 100%;
  max-width: var(--mc-width);
  background: var(--c-surface);
  color: var(--c-ink);
  font-family: var(--font);
  font-weight: var(--fw-body);
}
@media (min-width: 768px) {
  .mc-shell {
    max-width: var(--shell-wide, 560px);
  }
}
@media (min-width: 1024px) {
  .mc-shell {
    max-width: var(--shell-wide, 640px);
    box-shadow: var(--shadow);
    border-inline: 1px solid var(--c-border);
  }
}

.mc-head {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--c-header-bg);
  color: var(--c-header-ink);
  padding: var(--sp-4) var(--sp-5);
}
.mc-head-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.mc-greet {
  min-width: 0;
}
.mc-greet small {
  display: block;
  font-size: var(--fs-sm);
  opacity: 0.72;
}
.mc-greet b {
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
}
.mc-head-actions {
  margin-inline-start: auto;
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
}
.mc-progress {
  margin-top: var(--sp-4);
  background: color-mix(in srgb, var(--c-header-ink) 8%, transparent);
  border-radius: var(--radius);
  padding: var(--sp-3) var(--sp-4);
}

.mc-scroll {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.mc-nav {
  position: sticky;
  bottom: 0;
  z-index: 20;
  display: flex;
  gap: var(--sp-1);
  background: var(--c-surface-2);
  border-top: var(--border-width) solid var(--c-border);
  padding: var(--sp-2) var(--sp-2) calc(var(--sp-2) + env(safe-area-inset-bottom, 0px));
}
.mc-nav :slotted(*) {
  flex: 1;
  min-height: var(--tap-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-1);
  text-decoration: none;
  color: var(--c-muted);
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  border: none;
  background: none;
  border-radius: var(--radius);
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
@media (hover: hover) {
  .mc-nav :slotted(a:hover:not(.is-active)),
  .mc-nav :slotted(button:hover:not(:disabled):not(.is-active)) {
    color: var(--c-ink-soft);
    background: color-mix(in srgb, var(--c-ink) 6%, transparent);
  }
}
.mc-nav :slotted(.is-active),
.mc-nav :slotted([aria-current="page"]) {
  color: var(--c-accent-ink);
  background: color-mix(in srgb, var(--c-primary) 13%, transparent);
  font-weight: var(--fw-heading);
}
.mc-nav :slotted([aria-disabled="true"]),
.mc-nav :slotted(button:disabled) {
  opacity: 0.45;
  cursor: default;
}
.mc-nav :slotted(a:focus-visible),
.mc-nav :slotted(button:focus-visible) {
  outline: 3px solid var(--c-focus);
  outline-offset: -3px;
}
</style>
