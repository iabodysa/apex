<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <Teleport to="body">
    <Transition name="bpass-overlay">
      <div
        v-if="open"
        ref="overlay"
        class="bpass-overlay"
        :dir="dir"
        role="dialog"
        aria-modal="true"
        :aria-label="t('boarding.title')"
        @touchstart.passive="onTouchStart"
        @touchmove.passive="onTouchMove"
        @touchend="onTouchEnd"
      >
        <button class="bpass-overlay-x" :aria-label="t('common.close')" @click="close">
          <Icon name="x" :size="22" />
        </button>

        <div
          class="bpass-overlay-body"
          :style="dragStyle"
        >
          <BoardingPass :pass="pass" :trip="trip" />
        </div>

        <div class="bpass-overlay-hint" aria-hidden="true">
          <span class="bpass-overlay-handle"></span>
          <span class="bpass-overlay-hint-text">
            <Icon name="chevron" :size="14" class="bpass-overlay-chevup" />
            {{ t("boarding.swipeToClose") }}
          </span>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed } from "vue";
import { useOverlay } from "@shared/useOverlay.js";
import BoardingPass from "./BoardingPass.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const props = defineProps({
  open: { type: Boolean, default: false },
  pass: { type: Object, required: true },
  trip: { type: Object, default: null },
});
const emit = defineEmits(["close"]);

const { t, dir } = useI18n();

const overlay = ref(null);

function close() {
  emit("close");
}

useOverlay({ active: () => props.open, container: overlay, close });

const THRESHOLD = 70;
const startY = ref(0);
const dragY = ref(0);
const dragging = ref(false);

function onTouchStart(e) {
  if (!e.touches || !e.touches.length) return;
  startY.value = e.touches[0].clientY;
  dragging.value = true;
}
function onTouchMove(e) {
  if (!dragging.value || !e.touches || !e.touches.length) return;
  const dy = e.touches[0].clientY - startY.value;
  dragY.value = Math.min(0, dy);
}
function onTouchEnd() {
  if (!dragging.value) return;
  dragging.value = false;
  if (dragY.value <= -THRESHOLD) {
    dragY.value = 0;
    close();
  } else {
    dragY.value = 0;
  }
}

const dragStyle = computed(() => ({
  transform: `translateY(${dragY.value}px)`,
  opacity: String(Math.max(0.4, 1 + dragY.value / 260)),
  transition: dragging.value ? "none" : "transform 0.2s ease, opacity 0.2s ease",
}));
</script>

<style scoped>
.bpass-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: max(24px, env(safe-area-inset-top)) 20px max(24px, env(safe-area-inset-bottom));
  background: color-mix(in srgb, var(--c-canvas) 86%, var(--c-scrim));
  backdrop-filter: blur(6px);
  touch-action: none;
  overflow: hidden;
}

.bpass-overlay-x {
  position: absolute;
  top: max(14px, env(safe-area-inset-top));
  inset-inline-end: 16px;
  display: grid;
  place-items: center;
  height: var(--tap-min);
  width: var(--tap-min);
  border-radius: var(--radius-pill);
  background: var(--c-surface);
  color: var(--c-ink);
  border: var(--border-width) solid var(--c-border);
  box-shadow: var(--shadow-lg);
  cursor: pointer;
}
.bpass-overlay-x:active {
  transform: scale(0.94);
}
@media (hover: hover) {
  .bpass-overlay-x:hover {
    background: color-mix(in srgb, var(--c-ink) 6%, var(--c-surface));
  }
}

.bpass-overlay-body {
  width: 100%;
  max-width: 360px;
  will-change: transform;
}

.bpass-overlay-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--c-muted);
}
.bpass-overlay-handle {
  height: 4px;
  width: 44px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-ink) 28%, transparent);
}
.bpass-overlay-hint-text {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.bpass-overlay-chevup {
  transform: rotate(-90deg);
}

.bpass-overlay-enter-active,
.bpass-overlay-leave-active {
  transition: opacity 0.22s ease;
}
.bpass-overlay-enter-from,
.bpass-overlay-leave-to {
  opacity: 0;
}
.bpass-overlay-enter-active .bpass-overlay-body,
.bpass-overlay-leave-active .bpass-overlay-body {
  transition: transform 0.24s cubic-bezier(0.16, 1, 0.3, 1);
}
.bpass-overlay-enter-from .bpass-overlay-body,
.bpass-overlay-leave-to .bpass-overlay-body {
  transform: translateY(16px);
}
</style>
