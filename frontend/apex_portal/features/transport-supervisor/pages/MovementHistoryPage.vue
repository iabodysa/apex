<script setup>
import { Badge, createResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const history = createResource({
  url: "apex.salis.api.route_supervisor.get_movement_history",
  method: "GET",
  auto: false,
});
</script>

<template>
  <SupervisorCollection
    title="سجل الحركة"
    description="سجل زمني للرحلات المكتملة والملغاة للرجوع السريع."
    icon="clock"
    :resource="history"
    :collections="['items']"
    empty="لا توجد رحلات سابقة في السجل."
  >
    <template #default="{ rows }">
      <ol class="supervisor-history">
        <li v-for="trip in rows" :key="trip.name">
          <span class="supervisor-history__marker" aria-hidden="true" />
          <div class="supervisor-history__copy">
            <strong dir="auto">{{ recordTitle(trip, ['route_name', 'shift_name'], 'حركة سابقة') }}</strong>
            <bdi class="record-reference" dir="auto" translate="no">{{ trip.name }}</bdi>
            <span>{{ dateTimeLabel(trip.trip_date) || 'التاريخ غير محدد' }}</span>
            <small dir="auto">{{ trip.driver || 'السائق غير مسند' }} · <bdi translate="no">{{ trip.vehicle || 'المركبة غير مسندة' }}</bdi></small>
          </div>
          <Badge :theme="statusTheme(trip.status)" :label="statusLabel(trip.status)" />
        </li>
      </ol>
    </template>
  </SupervisorCollection>
</template>
