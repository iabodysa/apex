<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <button
    type="button"
    class="trip-row"
    :class="{ 'is-open': open }"
    :aria-current="open ? 'true' : undefined"
    @click="$emit('open')"
  >
    <span class="trip-head">
      <span class="trip-mark" :class="'mark-' + tone">
        <Icon :name="markIcon" :size="20" />
      </span>
      <span class="trip-title"><bdi>{{ trip.route_plan || trip.name }}</bdi></span>
      <Badge class="tone-badge" :theme="badgeTheme" variant="subtle" size="lg" :label="badgeLabel" />
    </span>

    <span class="trip-meta">
      <span v-if="trip.trip_date" class="trip-fact">
        {{ t("trips.date") }} <bdi>{{ fmtDate(trip.trip_date) }}</bdi>
      </span>
      <span v-if="trip.vehicle" class="trip-fact">
        {{ t("home.vehicle") }} <bdi>{{ trip.vehicle }}</bdi>
      </span>
      <span v-if="trip.depart_time" class="trip-fact">
        {{ t("home.depart") }} <bdi>{{ fmtTime(trip.depart_time) }}</bdi>
      </span>
      <span v-if="trip.return_time" class="trip-fact">
        {{ t("home.return") }} <bdi>{{ fmtTime(trip.return_time) }}</bdi>
      </span>
    </span>

    <span v-if="showBoarding" class="trip-board">
      <Progress class="board-bar" :value="boardedPercent" size="lg" />
      <span class="trip-board-label">
        {{ t("trips.boardedOf", { n: n(boarded), m: n(expected) }) }}
      </span>
    </span>
  </button>
</template>

<script setup>
import { computed } from "vue";
import { Badge, Progress } from "frappe-ui";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";
import { tripTone, tripStateLabel } from "../trips";

const { t, n, fmtTime, fmtDate, te } = useI18n();

const props = defineProps({
  trip: { type: Object, required: true },
  open: { type: Boolean, default: false },
  showBoarding: { type: Boolean, default: false },
});

defineEmits(["open"]);

const tone = computed(() => tripTone(props.trip));

const MARK_ICONS = {
  done: "badge",
  cancelled: "x",
  running: "route",
  planned: "calendar",
};
const markIcon = computed(() => MARK_ICONS[tone.value]);

const BADGE_THEMES = {
  done: "green",
  cancelled: "gray",
  running: "green",
  planned: "blue",
};
const badgeTheme = computed(() => BADGE_THEMES[tone.value]);
const badgeLabel = computed(() => tripStateLabel(props.trip, t, te));

const boarded = computed(() => props.trip.boarded_count || 0);
const expected = computed(() => props.trip.expected_count || 0);
const boardedPercent = computed(() =>
  expected.value ? Math.round((boarded.value / expected.value) * 100) : 0,
);
</script>

<style scoped>
.trip-row {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  width: 100%;
  min-height: var(--tap-md);
  padding: var(--sp-3) var(--sp-2);
  border: none;
  border-top: var(--border-width) solid var(--c-border);
  background: none;
  text-align: start;
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
  border-radius: var(--radius-sm);
}
.trip-row:first-child {
  border-top: none;
}
.trip-row:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: -3px;
}
.trip-row.is-open {
  background: color-mix(in srgb, var(--c-primary) 8%, transparent);
}

.trip-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.trip-mark {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  height: var(--sp-8);
  width: var(--sp-8);
  border-radius: var(--radius-sm);
}
.mark-planned {
  background: var(--c-info-bg);
  color: var(--c-info);
}
.mark-running {
  background: color-mix(in srgb, var(--c-primary) 12%, transparent);
  color: var(--c-primary);
}
.mark-done {
  background: var(--c-success-bg);
  color: var(--c-success);
}
.mark-cancelled {
  background: color-mix(in srgb, var(--c-ink) 8%, transparent);
  color: var(--c-muted);
}
.trip-title {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.35;
}

.trip-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-1) var(--sp-4);
  padding-inline-start: calc(var(--sp-8) + var(--sp-3));
}
.trip-fact {
  font-size: var(--fs-sm);
  color: var(--c-muted);
}

.trip-board {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  padding-inline-start: calc(var(--sp-8) + var(--sp-3));
}
.trip-board-label {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-ink-soft);
}
</style>
