<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <Panel :title="t('trips.summary')">
    <template #status>
      <Badge class="tone-badge" :theme="allDone ? 'green' : 'blue'" variant="subtle" size="lg" :label="doneLabel" />
    </template>

    <dl class="totals">
      <div class="total">
        <dt>{{ t("trips.todayTrips") }}</dt>
        <dd><bdi>{{ n(trips.length) }}</bdi></dd>
      </div>
      <div class="total">
        <dt>{{ t("trips.completedTrips") }}</dt>
        <dd><bdi>{{ n(completed) }}</bdi></dd>
      </div>
      <div class="total">
        <dt>{{ t("trips.totalBoarded") }}</dt>
        <dd><bdi>{{ n(boarded) }}</bdi></dd>
      </div>
    </dl>
  </Panel>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";
import Panel from "@shared/components/Panel.vue";
import { useI18n } from "../i18n";
import { tripTone } from "../trips";

const { t, n } = useI18n();

const props = defineProps({
  trips: { type: Array, required: true },
});

const completed = computed(() => props.trips.filter((trip) => tripTone(trip) === "done").length);
const boarded = computed(() =>
  props.trips.reduce((sum, trip) => sum + (trip.boarded_count || 0), 0),
);
const allDone = computed(() => props.trips.length > 0 && completed.value === props.trips.length);
const doneLabel = computed(() =>
  t("trips.doneOf", { n: n(completed.value), m: n(props.trips.length) }),
);
</script>

<style scoped>
.totals {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3) var(--sp-6);
}
.total dt {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
  letter-spacing: 0.02em;
}
.total dd {
  font-size: var(--fs-h1);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.15;
}
</style>
