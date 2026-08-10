<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="fleet-shell">
    <header class="fleet-top">
      <span class="fleet-brand"><slot name="brand" /></span>
      <nav class="fleet-nav"><slot name="nav" /></nav>
      <span class="fleet-actions"><slot name="actions" /></span>
    </header>

    <main class="fleet-body" :class="{ 'has-bottom-nav': !!$slots.nav }" :style="bodyStyle">
      <div v-if="$slots.heading || title" class="fleet-heading">
        <slot name="heading">
          <h1 class="fleet-hello">{{ title }}</h1>
          <p v-if="subtitle" class="fleet-sub">{{ subtitle }}</p>
        </slot>
      </div>

      <slot />

      <footer v-if="$slots.footer" class="fleet-footer"><slot name="footer" /></footer>
    </main>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  maxWidth: { type: [Number, String], default: "" },
});

const bodyStyle = computed(() => {
  if (!props.maxWidth) return undefined;
  const value = typeof props.maxWidth === "number" ? props.maxWidth + "px" : props.maxWidth;
  return { "--fleet-content-limit": value };
});
</script>

<style scoped>
.fleet-shell {
  --fleet-header-offset: 72px;
  min-height: 100vh;
  min-height: 100dvh;
  min-inline-size: 0;
  overflow-x: clip;
  background: var(--c-canvas);
  color: var(--c-ink);
  font-family: var(--font);
  font-weight: var(--fw-body);
}

.fleet-top {
  position: sticky;
  inset-block-start: 0;
  z-index: 20;
  display: flex;
  min-block-size: var(--fleet-header-offset);
  align-items: center;
  gap: var(--sp-3);
  padding: 14px clamp(var(--sp-4), 4vw, var(--sp-8));
  background: var(--c-header-bg);
  color: var(--c-header-ink);
  overflow: hidden;
}
.fleet-top::after {
  content: "";
  position: absolute;
  inset-block: -180%;
  inset-inline-end: clamp(5rem, 24vw, 24rem);
  inline-size: 1px;
  background: var(--c-header-accent);
  opacity: 0.3;
  transform: rotate(24deg);
  pointer-events: none;
}
.fleet-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-weight: var(--fw-heading);
}
.fleet-nav {
  margin-inline-start: auto;
  display: flex;
  align-items: center;
  gap: var(--sp-1);
}
.fleet-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
}
.fleet-nav:empty + .fleet-actions {
  margin-inline-start: auto;
}

.fleet-nav :slotted(a) {
  display: inline-flex;
  align-items: center;
  min-height: var(--tap-min);
  font-size: var(--fs-sm);
  color: color-mix(in srgb, var(--c-header-ink) 78%, transparent);
  text-decoration: none;
  padding: 7px var(--sp-3);
  border-radius: var(--radius-sm);
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}
@media (hover: hover) {
  .fleet-nav :slotted(a:not(.is-active):hover) {
    background: color-mix(in srgb, var(--c-header-ink) 10%, transparent);
    color: var(--c-header-ink);
  }
}
.fleet-nav :slotted(a.is-active),
.fleet-nav :slotted(a[aria-current="page"]) {
  background: color-mix(in srgb, var(--c-header-accent) 20%, transparent);
  color: var(--c-header-ink);
  font-weight: var(--fw-semibold);
}
.fleet-nav :slotted(a[aria-disabled="true"]) {
  opacity: 0.45;
  cursor: default;
  background: none;
}
.fleet-nav :slotted(a:focus-visible) {
  outline: 3px solid var(--c-header-accent);
  outline-offset: 2px;
}

.fleet-body {
  inline-size: 100%;
  max-inline-size: var(--fleet-content-limit, none);
  min-inline-size: 0;
  margin-inline: auto;
  padding: clamp(var(--sp-5), 4vw, 34px) clamp(var(--sp-4), 4vw, var(--sp-8)) 80px;
}
.fleet-heading {
  margin-bottom: 22px;
}
.fleet-hello {
  margin: 0 0 3px;
  max-inline-size: 22ch;
  font-family: var(--font-display);
  font-size: var(--fs-h1);
  font-weight: 700;
  text-wrap: balance;
}
.fleet-sub {
  margin: 0;
  color: var(--c-muted);
  font-family: var(--font-serif);
  font-size: var(--fs-body);
  line-height: 1.65;
}
.fleet-footer {
  margin-top: 48px;
  padding: 22px var(--sp-6);
  border-block: var(--border-width) solid var(--c-border-strong);
}

@media (max-width: 767px) {
  .fleet-top {
    min-block-size: 64px;
  }
  .fleet-nav {
    position: fixed;
    z-index: 25;
    inset-inline: 0;
    inset-block-end: 0;
    justify-content: stretch;
    gap: var(--sp-1);
    margin: 0;
    padding: var(--sp-1) var(--sp-2) calc(var(--sp-1) + env(safe-area-inset-bottom, 0px));
    border-block-start: 1px solid var(--c-border);
    background: var(--c-surface);
  }
  .fleet-nav :slotted(a) {
    flex: 1 1 0;
    justify-content: center;
    min-inline-size: 0;
    min-block-size: var(--tap-lg);
    color: var(--c-muted);
    text-align: center;
  }
  .fleet-nav :slotted(a.is-active),
  .fleet-nav :slotted(a[aria-current="page"]) {
    background: color-mix(in srgb, var(--c-primary) 10%, transparent);
    color: var(--c-primary);
  }
  .fleet-body.has-bottom-nav {
    padding-block-end: calc(5rem + env(safe-area-inset-bottom, 0px));
  }
}
</style>
