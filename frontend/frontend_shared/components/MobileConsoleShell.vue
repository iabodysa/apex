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
});
</script>

<style scoped>
/* DESIGN.md §1 — header, frame, navbar, and nothing else. The frame is the ONLY element
   that scrolls; two nested scrollers is what makes a phone feel broken. */
.mc-shell {
  display: flex;
  flex-direction: column;
  block-size: 100vh;
  block-size: 100dvh;
  inline-size: 100%;
  background: var(--c-canvas);
  color: var(--c-ink);
  font-family: var(--font);
  font-weight: var(--fw-body);
}

.mc-head {
  position: sticky;
  inset-block-start: 0;
  z-index: 20;
  flex: 0 0 auto;
  padding: 14px var(--sp-5) var(--sp-4);
  background: var(--c-surface);
  border-block-end: 1px solid var(--c-border);
}
.mc-head-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  max-inline-size: var(--mc-max, 1100px);
  margin-inline: auto;
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
  color: var(--c-muted);
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
  max-inline-size: var(--mc-max, 1100px);
  margin: var(--sp-2) auto 0;
}

.mc-body {
  flex: 1 1 auto;
  display: flex;
  min-block-size: 0;
  inline-size: 100%;
}

/* The frame owns the scroll. */
.mc-frame {
  flex: 1 1 auto;
  min-inline-size: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

/* §2 — the primary action lives at the bottom of the frame, full width, and does not
   scroll away. A destructive action never goes here. */
.mc-action {
  position: sticky;
  inset-block-end: 0;
  margin-block-start: auto;
  padding-block-start: var(--sp-3);
  background: linear-gradient(to top, var(--c-canvas) 70%, transparent);
}
.mc-action :slotted(button) {
  inline-size: 100%;
  min-block-size: var(--tap-lg);
}

.mc-list {
  display: none;
}

/* The side rail only exists on the desktop row. */
.mc-rail {
  display: none;
}

/* §1 — sticky bottom navbar, destinations only, --tap-lg tall. */
.mc-nav {
  flex: 0 0 auto;
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
.mc-nav :slotted(button.is-active) {
  color: var(--c-primary);
  background: var(--c-primary-soft, transparent);
}

/* --bp-tablet 768: the column gains breathing room, still one column. */
@media (min-width: 768px) {
  .mc-frame {
    max-inline-size: 560px;
    margin-inline: auto;
    inline-size: 100%;
    padding: var(--sp-5);
  }
}

/* --bp-desktop 1024: the contract's desktop row — frame min(100%, 1100px) centred, TWO
   panes where the screen has a list, and the navbar becomes a side rail. Before this, all
   four field portals drew the same narrow column at 1440 and left the screen empty. */
@media (min-width: 1024px) {
  .mc-body {
    max-inline-size: 1100px;
    margin-inline: auto;
    gap: var(--sp-4);
    padding-inline: var(--sp-4);
  }
  .mc-nav {
    display: none;
  }
  .mc-rail {
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
    flex: 0 0 220px;
    padding-block: var(--sp-4);
    border-inline-end: 1px solid var(--c-border);
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
    color: var(--c-muted);
    font-size: var(--fs-body);
    font-weight: var(--fw-semibold);
    text-decoration: none;
    border-radius: var(--radius-sm);
  }
  .mc-rail :slotted(a.is-active),
  .mc-rail :slotted(button.is-active) {
    color: var(--c-primary);
    background: var(--c-surface-2);
  }
  .mc-body.has-list .mc-list {
    display: block;
    flex: 0 0 380px;
    min-inline-size: 360px;
    max-inline-size: 420px;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding-block: var(--sp-4);
    border-inline-end: 1px solid var(--c-border);
  }
  .mc-frame {
    max-inline-size: none;
    margin-inline: 0;
  }
}
</style>
