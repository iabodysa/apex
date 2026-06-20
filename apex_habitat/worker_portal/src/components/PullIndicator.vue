<!-- [T-320] Pull-to-refresh indicator: a small spinner that slides down and fades
     in as the page is pulled past its top, then spins continuously while the
     refresh resolves. Driven by usePullToRefresh (distance / refreshing).

     Positioning uses LOGICAL properties only and is horizontally CENTERED
     (inset-inline: 0 + margin-inline: auto), so it reads identically under LTR
     and RTL with NO direction-keyed selector — avoiding the scoped [dir=rtl]
     pitfall (T-297). aria-hidden: a purely decorative progress affordance. -->
<template>
  <div
    v-if="distance > 0 || refreshing"
    class="ptr"
    :style="indicatorStyle"
    aria-hidden="true"
  >
    <div class="spinner ptr-spinner" :class="{ 'ptr-paused': !refreshing }" :style="spinnerStyle"></div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  // px the page is currently pulled (already resisted/clamped).
  distance: { type: Number, default: 0 },
  // true while the refresh promise is in flight.
  refreshing: { type: Boolean, default: false },
  // px pull at which a release triggers a refresh (drives the fade ramp).
  threshold: { type: Number, default: 70 },
});

// Translate the indicator down with the pull; while refreshing it parks at a
// fixed resting offset so the spinner sits just below the top edge.
const offset = computed(() => (props.refreshing ? 44 : Math.min(props.distance, 70) + 4));

// Fade + scale in proportionally to how close the pull is to the threshold; a
// refreshing indicator is always fully shown.
const ratio = computed(() =>
  props.refreshing ? 1 : Math.min(props.distance / props.threshold, 1),
);

const indicatorStyle = computed(() => ({
  transform: `translateY(${offset.value}px)`,
  // No JS-animated spring on the parked state; CSS transition handles release.
  transition: props.refreshing ? "transform 0.2s ease" : "transform 0.18s ease",
}));

const spinnerStyle = computed(() => ({
  opacity: ratio.value,
  // Spinner grows from 70% → 100% as the pull approaches the threshold.
  transform: `scale(${0.7 + ratio.value * 0.3})`,
}));
</script>

<style scoped>
/* Pinned to the top, horizontally centered via logical inset + auto margins —
   symmetric, so no [dir=rtl] rule is needed (T-297-safe). pointer-events:none so
   it never intercepts the touch gesture it visualizes. */
.ptr {
  position: fixed;
  inset-block-start: 0;
  inset-inline: 0;
  z-index: 30;
  display: flex;
  justify-content: center;
  margin-block-start: -8px;
  pointer-events: none;
}
.ptr-spinner {
  height: 28px;
  width: 28px;
  border-width: 3px;
}
/* While pulling (not yet refreshing) the rotation animation is paused — the
   spinner only spins once the refresh is actually running. */
.ptr-paused {
  animation: none;
}
@media (prefers-reduced-motion: reduce) {
  .ptr-spinner {
    animation: none;
  }
}
</style>
