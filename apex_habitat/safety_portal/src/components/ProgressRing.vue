<!-- Animated SVG progress ring: the "rated X / total" indicator on each cadence
     header. The stroke-dashoffset transitions, so the ring sweeps closed as the
     supervisor taps tasks. Colour shifts from accent (in progress) to success
     (complete). Pure SVG + CSS — no chart dependency. -->
<template>
  <div class="ring" :style="{ width: size + 'px', height: size + 'px' }">
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" class="ring-svg">
      <circle
        class="ring-track"
        :cx="c"
        :cy="c"
        :r="r"
        fill="none"
        :stroke-width="stroke"
      />
      <circle
        class="ring-fill"
        :class="{ 'ring-fill-done': done >= total && total > 0 }"
        :cx="c"
        :cy="c"
        :r="r"
        fill="none"
        :stroke-width="stroke"
        stroke-linecap="round"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="offset"
      />
    </svg>
    <div class="ring-label">
      <span class="ring-done">{{ done }}</span>
      <span class="ring-total">/{{ total }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  done: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  size: { type: Number, default: 56 },
  stroke: { type: Number, default: 5 },
});

const c = computed(() => props.size / 2);
const r = computed(() => props.size / 2 - props.stroke);
const circumference = computed(() => 2 * Math.PI * r.value);
const offset = computed(() => {
  const pct = props.total > 0 ? Math.min(props.done / props.total, 1) : 0;
  return circumference.value * (1 - pct);
});
</script>

<style scoped>
.ring {
  position: relative;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
/* Start the sweep at 12 o'clock. */
.ring-svg {
  transform: rotate(-90deg);
}
:global([dir="rtl"]) .ring-svg {
  transform: rotate(-90deg) scaleX(-1);
}
.ring-track {
  stroke: color-mix(in srgb, var(--c-ink) 10%, transparent);
}
.ring-fill {
  stroke: var(--c-mint);
  transition:
    stroke-dashoffset 0.5s cubic-bezier(0.22, 1, 0.36, 1),
    stroke 0.3s ease;
}
.ring-fill-done {
  stroke: var(--c-success);
}
.ring-label {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-weight: var(--fw-heading);
  line-height: 1;
}
.ring-done {
  font-size: 15px;
  color: var(--c-ink);
}
.ring-total {
  font-size: 11px;
  color: var(--c-muted);
}
</style>
