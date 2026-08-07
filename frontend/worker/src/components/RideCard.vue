<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <Panel :title="t('home.nextRide')">
    <template v-if="ride && ride.status" #status>
      <Badge
        class="tone-badge"
        :theme="statusTheme"
        variant="subtle"
        size="lg"
        :label="tEnum('transportStatus', ride.status)"
      />
    </template>

    <template v-if="ride">
      <p class="ride-title">
        {{ ride.request_type ? tEnum("requestType", ride.request_type) : ride.transport_request }}
      </p>

      <p v-if="etaMinutes !== null" class="ride-live">
        <span class="eta-dot" aria-hidden="true"></span>
        <span>{{ t("home.etaArriving", { eta: etaMinutes }) }}</span>
      </p>
      <p v-else-if="enRoute" class="ride-live">
        <span class="eta-dot" aria-hidden="true"></span>
        <span>{{ t("home.enRoute") }}</span>
      </p>

      <dl class="ride-facts">
        <div v-if="ride.pickup_point" class="ride-fact ride-fact-wide">
          <dt>{{ t("transport.pickupPoint") }}</dt>
          <dd>{{ ride.pickup_point }}</dd>
        </div>
        <div v-if="departs" class="ride-fact">
          <dt>{{ t("transport.departs") }}</dt>
          <dd>
            <bdi>{{ departs }}</bdi>
            <span v-if="relativeHint" class="ride-when">{{ relativeHint }}</span>
          </dd>
        </div>
        <div v-if="plate" class="ride-fact">
          <dt>{{ t("transport.plate") }}</dt>
          <dd><bdi>{{ plate }}</bdi></dd>
        </div>
        <div v-if="driverName" class="ride-fact">
          <dt>{{ t("transport.driver") }}</dt>
          <dd>{{ driverName }}</dd>
        </div>
      </dl>
    </template>

    <EmptyState v-else :title="t('home.noRide')" :hint="t('home.noRideHint')">
      <template #icon><Icon name="route" :size="22" /></template>
      <template #action>
        <Button
          class="row-btn"
          variant="outline"
          route="/request-transport"
          :label="t('transport.requestNew')"
        >
          <template #prefix><Icon name="plus" :size="16" /></template>
        </Button>
      </template>
    </EmptyState>
  </Panel>
</template>

<script setup>
import { computed } from "vue";
import { TRIP } from "@shared/statusVocabularies";
import { Badge, Button } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import Panel from "@shared/components/Panel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";
import { formatTime, formatDateTime } from "../utils/datetime";

const { t, tEnum } = useI18n();

const props = defineProps({
  ride: { type: Object, default: null },
  relativeHint: { type: String, default: "" },
});

const departs = computed(() => {
  const r = props.ride;
  if (!r) return "";
  if (r.depart_time) return formatTime(r.depart_time);
  return r.pickup_datetime ? formatDateTime(r.pickup_datetime) : "";
});

const plate = computed(() => props.ride?.vehicle?.plate_number || "");
const driverName = computed(() => props.ride?.driver?.full_name || "");

const etaMinutes = computed(() => {
  const m = props.ride?.eta_minutes;
  return m === null || m === undefined ? null : m;
});

const enRoute = computed(() => props.ride?.trip_status === TRIP.DISPATCHED);

const statusTheme = computed(() => (enRoute.value ? "green" : "blue"));
</script>

<style scoped>
.ride-title {
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.3;
}
.ride-live {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-2);
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-primary);
}
.ride-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3) var(--sp-5);
  margin-top: var(--sp-4);
}
.ride-fact {
  min-width: 0;
}
.ride-fact-wide {
  flex-basis: 100%;
}
.ride-fact dt {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
  letter-spacing: 0.02em;
}
.ride-fact dd {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  line-height: 1.4;
}
.ride-when {
  font-weight: var(--fw-body);
  color: var(--c-muted);
}
</style>
