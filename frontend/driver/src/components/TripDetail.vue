<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <component :is="framed ? Panel : 'div'" :title="framed ? t('trips.detailTitle') : undefined">
    <div class="detail-head">
      <p class="detail-title"><bdi>{{ trip.route_plan || trip.name }}</bdi></p>
      <Badge class="tone-badge" :theme="badgeTheme" variant="subtle" size="lg" :label="badgeLabel" />
    </div>

    <dl class="detail-facts">
      <div v-if="trip.trip_date" class="detail-fact">
        <dt>{{ t("trips.date") }}</dt>
        <dd><bdi>{{ fmtDate(trip.trip_date) }}</bdi></dd>
      </div>
      <div v-if="trip.vehicle" class="detail-fact">
        <dt>{{ t("home.vehicle") }}</dt>
        <dd><bdi>{{ trip.vehicle }}</bdi></dd>
      </div>
      <div v-if="trip.depart_time" class="detail-fact">
        <dt>{{ t("home.depart") }}</dt>
        <dd><bdi>{{ fmtTime(trip.depart_time) }}</bdi></dd>
      </div>
      <div v-if="trip.return_time" class="detail-fact">
        <dt>{{ t("home.return") }}</dt>
        <dd><bdi>{{ fmtTime(trip.return_time) }}</bdi></dd>
      </div>
    </dl>

    <div v-if="showBoarding" class="detail-board">
      <Progress class="board-bar" :value="boardedPercent" size="lg" />
      <p class="detail-board-label">
        {{ t("trips.boardedOf", { n: n(trip.boarded_count || 0), m: n(trip.expected_count) }) }}
      </p>
    </div>

    <div class="detail-actions">
      <Button
        class="row-btn"
        variant="outline"
        :route="'/route/' + encodeURIComponent(trip.name)"
        :label="t('trips.fullRoute')"
      >
        <template #prefix><Icon name="route" :size="16" /></template>
      </Button>

      <Button
        v-if="trip.google_maps_url"
        class="row-btn"
        variant="ghost"
        :link="trip.google_maps_url"
        :label="t('route.openMap')"
      >
        <template #prefix><Icon name="map-pin" :size="16" /></template>
      </Button>

      <template v-if="canBoard">
        <Button class="row-btn" variant="outline" :label="t('trips.scanBoarding')" @click="$emit('scan')">
          <template #prefix><Icon name="qr" :size="16" /></template>
        </Button>
        <Button class="row-btn" variant="ghost" :label="t('trips.manualBoarding')" @click="$emit('manual')">
          <template #prefix><Icon name="user" :size="16" /></template>
        </Button>
      </template>

      <Button
        v-if="canComplete"
        class="row-btn"
        variant="outline"
        :loading="busy"
        :loading-text="t('trips.completing')"
        :label="t('trips.complete')"
        @click="$emit('complete')"
      >
        <template #prefix><Icon name="badge" :size="16" /></template>
      </Button>
    </div>

    <p v-if="closed" class="detail-note">{{ t("trips.closedNote") }}</p>
  </component>
</template>

<script setup>
import { computed } from "vue";
import { Badge, Button, Progress } from "frappe-ui";
import Panel from "@shared/components/Panel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";
import { tripTone, tripStateLabel } from "../trips";

const { t, n, fmtTime, fmtDate, te } = useI18n();

const props = defineProps({
  trip: { type: Object, required: true },
  live: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  framed: { type: Boolean, default: true },
});

defineEmits(["scan", "manual", "complete"]);

const tone = computed(() => tripTone(props.trip));

const BADGE_THEMES = {
  done: "green",
  cancelled: "gray",
  running: "green",
  planned: "blue",
};
const badgeTheme = computed(() => BADGE_THEMES[tone.value]);
const badgeLabel = computed(() => tripStateLabel(props.trip, t, te));

const closed = computed(() => tone.value === "done" || tone.value === "cancelled");
const showBoarding = computed(() => props.live && !!props.trip.expected_count);
const canBoard = computed(() => props.live && tone.value === "running" && !!props.trip.expected_count);
const canComplete = computed(() => props.live && tone.value === "running");

const boardedPercent = computed(() => {
  const expected = props.trip.expected_count || 0;
  if (!expected) return 0;
  return Math.round(((props.trip.boarded_count || 0) / expected) * 100);
});
</script>

<style scoped>
.detail-head {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
}
.detail-title {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.35;
}
.detail-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3) var(--sp-6);
  margin-top: var(--sp-4);
}
.detail-fact dt {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
  letter-spacing: 0.02em;
}
.detail-fact dd {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
}
.detail-board {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  margin-top: var(--sp-4);
}
.detail-board-label {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-ink-soft);
}
.detail-actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(calc(var(--sp-8) * 5), 1fr));
  gap: var(--sp-2);
  margin-top: var(--sp-4);
}
.detail-note {
  margin-top: var(--sp-3);
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
</style>
