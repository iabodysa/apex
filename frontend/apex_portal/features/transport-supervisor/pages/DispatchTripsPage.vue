<script setup>
import { Badge, FeatherIcon, createResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const trips = createResource({
  url: "apex.salis.api.route_supervisor.get_dispatch_trips",
  method: "GET",
  auto: false,
});
</script>

<template>
  <SupervisorCollection
    title="الرحلات"
    description="رحلات التشغيل الحالية مع السائق والمركبة وحالة التنفيذ."
    icon="navigation"
    :resource="trips"
    :collections="['trips']"
    empty="لا توجد رحلات تشغيل حالياً."
  >
    <template #default="{ rows }">
      <ol class="supervisor-trip-board">
        <li v-for="trip in rows" :key="trip.name">
          <RouterLink :to="`/trips/${encodeURIComponent(trip.name)}`">
            <div class="supervisor-trip-date">
              <span>موعد الرحلة</span>
              <strong><bdi>{{ dateTimeLabel(trip.trip_date) || 'غير محدد' }}</bdi></strong>
            </div>
            <div class="record-identity">
              <strong dir="auto">{{ recordTitle(trip, ['route_name', 'shift_name'], 'رحلة تشغيل') }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ trip.name }}</bdi>
              <span dir="auto">{{ trip.driver || 'السائق غير مسند' }} · <bdi translate="no">{{ trip.vehicle || 'المركبة غير مسندة' }}</bdi></span>
            </div>
            <Badge :theme="statusTheme(trip.status)" :label="statusLabel(trip.status)" />
            <FeatherIcon class="supervisor-row-chevron" name="arrow-left" aria-hidden="true" />
          </RouterLink>
        </li>
      </ol>
    </template>
  </SupervisorCollection>
</template>
