<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="portal-frame" :class="{ 'has-navigation': !!$slots.nav }">
    <a v-if="skipLabel" class="portal-skip" href="#portal-main">{{ skipLabel }}</a>

    <header class="portal-masthead">
      <span class="portal-identity">
        <slot name="brand"><Brand variant="reverse" :size="30" /></slot>
      </span>
      <span class="portal-mast-actions"><slot name="header-actions" /></span>
    </header>

    <div
      class="portal-workspace"
      :class="{
        'has-queue': !!$slots.queue,
        'has-evidence': !!$slots.evidence,
      }"
    >
      <aside v-if="$slots.queue" class="portal-queue"><slot name="queue" /></aside>

      <main id="portal-main" class="portal-scene" tabindex="-1">
        <header v-if="title || eyebrow || subtitle" class="portal-scene-heading">
          <p v-if="eyebrow" class="portal-eyebrow">{{ eyebrow }}</p>
          <h1 v-if="title">{{ title }}</h1>
          <p v-if="subtitle" class="portal-scene-subtitle">{{ subtitle }}</p>
        </header>
        <div class="portal-scene-body"><slot /></div>
        <slot name="action" />
      </main>

      <aside v-if="$slots.evidence" class="portal-evidence"><slot name="evidence" /></aside>
    </div>

    <nav v-if="$slots.nav" class="portal-navigation" :aria-label="navigationLabel">
      <slot name="nav" />
    </nav>
  </div>
</template>

<script setup>
import Brand from "./Brand.vue";

defineProps({
  title: { type: String, default: "" },
  eyebrow: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  navigationLabel: { type: String, default: "Navigation" },
  skipLabel: { type: String, default: "" },
});
</script>

<style scoped>
.portal-frame {
  display: grid;
  grid-template-areas:
    "masthead"
    "workspace"
    "navigation";
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: auto minmax(0, 1fr) auto;
  block-size: 100vh;
  block-size: 100dvh;
  min-inline-size: 0;
  overflow: hidden;
  background: var(--c-canvas);
  color: var(--c-ink);
  font-family: var(--font);
}

.portal-skip {
  position: fixed;
  inset-block-start: var(--sp-3);
  inset-inline-start: var(--sp-3);
  z-index: 100;
  translate: 0 -180%;
  padding: var(--sp-2) var(--sp-4);
  border-radius: var(--radius-sm);
  background: var(--c-surface-2);
  color: var(--c-ink);
  font-weight: var(--fw-semibold);
}
.portal-skip:focus {
  translate: 0;
}

.portal-masthead {
  grid-area: masthead;
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-block-size: 64px;
  padding: var(--sp-3) clamp(var(--sp-4), 3vw, var(--sp-8));
  overflow: hidden;
  background: var(--c-header-bg);
  color: var(--c-header-ink);
}
.portal-masthead::after {
  content: "";
  position: absolute;
  z-index: -1;
  inset-block: -120%;
  inset-inline-end: clamp(4rem, 22vw, 22rem);
  inline-size: 1px;
  background: var(--c-header-accent);
  opacity: 0.34;
  transform: rotate(24deg);
  transform-origin: center;
}
.portal-identity,
.portal-mast-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  min-inline-size: 0;
}
.portal-mast-actions {
  margin-inline-start: auto;
}

.portal-workspace {
  grid-area: workspace;
  min-inline-size: 0;
  min-block-size: 0;
  overflow: auto;
  overscroll-behavior: contain;
  display: grid;
  align-items: start;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--sp-5);
  padding: clamp(var(--sp-4), 3vw, var(--sp-8));
}
.portal-scene,
.portal-queue,
.portal-evidence {
  min-inline-size: 0;
}
.portal-scene {
  outline: none;
}
.portal-scene:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: -3px;
}
.portal-scene-heading {
  padding-block-end: clamp(var(--sp-5), 4vw, var(--sp-8));
  border-block-end: 1px solid var(--c-border-strong);
  margin-block-end: clamp(var(--sp-5), 3vw, var(--sp-8));
}
.portal-eyebrow {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0 0 var(--sp-2);
  color: var(--c-accent-ink);
  font-family: var(--font-brand);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  text-transform: uppercase;
}
.portal-eyebrow::before {
  content: "";
  inline-size: 2rem;
  block-size: 1px;
  background: currentColor;
}
.portal-scene-heading h1 {
  margin: 0;
  max-inline-size: 22ch;
  color: var(--c-ink);
  font-family: var(--font-display);
  font-size: var(--fs-display);
  font-weight: 700;
  line-height: 1.12;
  text-wrap: balance;
}
.portal-scene-subtitle {
  max-inline-size: 62ch;
  margin: var(--sp-3) 0 0;
  color: var(--c-ink-soft);
  font-family: var(--font-serif);
  font-size: clamp(1rem, 0.4vw + 0.9rem, 1.2rem);
  line-height: 1.7;
}
.portal-scene-body {
  min-inline-size: 0;
}

.portal-navigation {
  grid-area: navigation;
  display: flex;
  align-items: stretch;
  gap: var(--sp-1);
  padding: var(--sp-1) var(--sp-2) calc(var(--sp-1) + env(safe-area-inset-bottom, 0px));
  border-block-start: 1px solid var(--c-border);
  background: var(--c-surface);
}
.portal-navigation :slotted(a),
.portal-navigation :slotted(button) {
  flex: 1 1 0;
  min-inline-size: 0;
  min-block-size: var(--tap-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-1);
  padding-inline: var(--sp-2);
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-muted);
  font-family: var(--font-brand);
  font-weight: var(--fw-semibold);
  text-decoration: none;
}
.portal-navigation :slotted(.is-active),
.portal-navigation :slotted([aria-current="page"]) {
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
  color: var(--c-primary);
}

@media (min-width: 56rem) {
  .portal-frame.has-navigation {
    grid-template-areas:
      "masthead masthead"
      "navigation workspace";
    grid-template-columns: max-content minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
  }
  .portal-navigation {
    flex-direction: column;
    align-items: stretch;
    justify-content: flex-start;
    inline-size: clamp(12rem, 18vw, 15rem);
    padding: var(--sp-5) var(--sp-3);
    border-block-start: 0;
    border-inline-end: 1px solid color-mix(in srgb, var(--c-header-ink) 14%, transparent);
    background: var(--c-header-bg);
  }
  .portal-navigation :slotted(a),
  .portal-navigation :slotted(button) {
    flex: 0 0 auto;
    justify-content: flex-start;
    color: color-mix(in srgb, var(--c-header-ink) 72%, transparent);
  }
  .portal-navigation :slotted(.is-active),
  .portal-navigation :slotted([aria-current="page"]) {
    background: color-mix(in srgb, var(--c-header-accent) 14%, transparent);
    color: var(--c-header-ink);
  }
  .portal-workspace.has-queue {
    grid-template-columns: minmax(16rem, 0.7fr) minmax(22rem, 1.3fr);
  }
  .portal-queue {
    position: sticky;
    inset-block-start: 0;
  }
}

@media (min-width: 76rem) {
  .portal-workspace.has-evidence:not(.has-queue) {
    grid-template-columns: minmax(28rem, 1.5fr) minmax(16rem, 0.5fr);
  }
  .portal-workspace.has-queue.has-evidence {
    grid-template-columns: minmax(16rem, 0.65fr) minmax(28rem, 1.35fr) minmax(16rem, 0.65fr);
  }
  .portal-evidence {
    position: sticky;
    inset-block-start: 0;
  }
}
</style>
