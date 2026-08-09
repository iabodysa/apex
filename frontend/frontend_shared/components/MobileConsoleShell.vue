<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="mc-shell">
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

    <div class="mc-body" :class="{ 'has-list': !!$slots.list }">
      <nav v-if="$slots.nav" class="mc-rail"><slot name="nav" /></nav>

      <aside v-if="$slots.list" class="mc-list"><slot name="list" /></aside>

      <main class="mc-frame">
        <slot />
        <div v-if="$slots.action" class="mc-action"><slot name="action" /></div>
      </main>
    </div>

    <nav v-if="$slots.nav" class="mc-nav"><slot name="nav" /></nav>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  // Kept while portals migrate. Composition now follows available content, not this hint.
  maxWidth: { type: [Number, String], default: "" },
});
</script>

<style scoped>
.mc-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  block-size: 100vh;
  block-size: 100dvh;
  min-inline-size: 0;
  inline-size: 100%;
  overflow: hidden;
  background: var(--c-canvas);
  color: var(--c-ink);
  font-family: var(--font);
  font-weight: var(--fw-body);
}

.mc-head {
  position: relative;
  z-index: 20;
  min-inline-size: 0;
  padding: var(--sp-3) clamp(var(--sp-4), 4vw, var(--sp-6));
  overflow: hidden;
  background: var(--c-header-bg);
  color: var(--c-header-ink);
}
.mc-head::after {
  content: "";
  position: absolute;
  inset-block: -160%;
  inset-inline-end: clamp(3rem, 24vw, 18rem);
  inline-size: 1px;
  background: var(--c-header-accent);
  opacity: 0.3;
  transform: rotate(24deg);
  pointer-events: none;
}
.mc-head-row {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  inline-size: 100%;
}
.mc-greet {
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
  flex: 1 1 auto;
}
.mc-greet small {
  font-size: var(--fs-xs);
  color: color-mix(in srgb, var(--c-header-ink) 70%, transparent);
}
.mc-greet b {
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mc-head-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex: 0 0 auto;
}
.mc-progress {
  position: relative;
  z-index: 1;
  margin-block-start: var(--sp-2);
}

.mc-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-block-size: 0;
  min-inline-size: 0;
  inline-size: 100%;
}

.mc-frame {
  min-inline-size: 0;
  min-block-size: 0;
  overflow-y: auto;
  overflow-x: clip;
  overscroll-behavior: contain;
  padding: clamp(var(--sp-4), 4vw, var(--sp-8));
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.mc-action {
  position: sticky;
  inset-block-end: 0;
  margin-block-start: auto;
  padding: var(--sp-3);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--c-surface) 94%, transparent);
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
}
.mc-action :slotted(button) {
  inline-size: 100%;
  min-block-size: var(--tap-lg);
}

.mc-list,
.mc-rail {
  display: none;
}

.mc-nav {
  display: flex;
  align-items: stretch;
  justify-content: space-around;
  gap: var(--sp-1);
  padding-inline: var(--sp-2);
  padding-block: var(--sp-1);
  padding-block-end: calc(var(--sp-1) + env(safe-area-inset-bottom, 0px));
  background: var(--c-surface);
  border-block-start: 1px solid var(--c-border);
}
.mc-nav :slotted(a),
.mc-nav :slotted(button) {
  flex: 1 1 0;
  min-block-size: var(--tap-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border: none;
  background: none;
  color: var(--c-muted);
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  text-decoration: none;
  border-radius: var(--radius-sm);
}
.mc-nav :slotted(a.is-active),
.mc-nav :slotted(a[aria-current="page"]),
.mc-nav :slotted(button.is-active) {
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
}

@media (min-width: 62rem) {
  .mc-body {
    grid-template-columns: max-content minmax(0, 1fr);
  }
  .mc-nav {
    display: none;
  }
  .mc-rail {
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
    inline-size: clamp(12rem, 17vw, 15rem);
    min-inline-size: 0;
    padding: var(--sp-5) var(--sp-3);
    border-inline-end: 1px solid color-mix(in srgb, var(--c-header-ink) 14%, transparent);
    background: var(--c-header-bg);
  }
  .mc-rail :slotted(a),
  .mc-rail :slotted(button) {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: var(--sp-3);
    min-block-size: var(--tap-md);
    padding-inline: var(--sp-3);
    border: none;
    background: none;
    color: color-mix(in srgb, var(--c-header-ink) 72%, transparent);
    font-size: var(--fs-body);
    font-weight: var(--fw-semibold);
    text-decoration: none;
    border-radius: var(--radius-sm);
  }
  .mc-rail :slotted(a.is-active),
  .mc-rail :slotted(a[aria-current="page"]),
  .mc-rail :slotted(button.is-active) {
    color: var(--c-header-ink);
    background: color-mix(in srgb, var(--c-header-accent) 14%, transparent);
  }
}

@media (min-width: 72rem) {
  .mc-body.has-list {
    grid-template-columns: max-content minmax(16rem, 0.72fr) minmax(24rem, 1.28fr);
  }
  .mc-body.has-list .mc-list {
    display: block;
    min-inline-size: 0;
    padding: var(--sp-5) var(--sp-4);
    border-inline-end: 1px solid var(--c-border);
    background: color-mix(in srgb, var(--c-surface) 74%, transparent);
  }
}
</style>
