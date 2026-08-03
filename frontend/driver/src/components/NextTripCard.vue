<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <Panel :title="t('home.nextTrip')">
    <template v-if="trip" #status>
      <Badge class="tone-badge" :theme="statusTheme" variant="subtle" size="lg" :label="statusLabel" />
    </template>

    <template v-if="trip">
      <p class="trip-title"><bdi>{{ trip.route_plan || trip.name }}</bdi></p>

      <dl class="trip-facts">
        <div v-if="trip.vehicle" class="trip-fact">
          <dt>{{ t("home.vehicle") }}</dt>
          <dd><bdi>{{ trip.vehicle }}</bdi></dd>
        </div>
        <div v-if="trip.depart_time" class="trip-fact">
          <dt>{{ t("home.depart") }}</dt>
          <dd><bdi>{{ fmtTime(trip.depart_time) }}</bdi></dd>
        </div>
        <div v-if="trip.return_time" class="trip-fact">
          <dt>{{ t("home.return") }}</dt>
          <dd><bdi>{{ fmtTime(trip.return_time) }}</bdi></dd>
        </div>
      </dl>

      <div class="trip-actions">
        <Button class="row-btn" variant="outline" :route="tripRoute" :label="t('home.viewTrip')">
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
      </div>
    </template>

    <EmptyState v-else :title="t('home.noTripToday')" :hint="t('home.noTripTodayHint')">
      <template #icon><Icon name="route" :size="22" /></template>
      <template #action>
        <Button class="row-btn" variant="outline" route="/trips" :label="t('home.myTrips')" />
      </template>
    </EmptyState>
  </Panel>
</template>

<script setup>
import { computed } from "vue";
import { Badge, Button } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import Panel from "./Panel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t, te, fmtTime } = useI18n();

const props = defineProps({
  trip: { type: Object, default: null },
});

const tripRoute = computed(() =>
  props.trip ? "/route/" + encodeURIComponent(props.trip.name) : "/trips",
);

const statusLabel = computed(() => {
  if (!props.trip) return "";
  if (props.trip.started) return t("trips.started");
  return te("tripStatus", props.trip.status);
});

const statusTheme = computed(() => (props.trip && props.trip.started ? "green" : "blue"));
</script>

<style scoped>
.trip-title {
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.35;
}
.trip-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-5);
  margin-top: var(--sp-3);
}
.trip-fact dt {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
  letter-spacing: 0.02em;
}
.trip-fact dd {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
}
.trip-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-top: var(--sp-4);
}
</style>
