<script setup>
import { Badge, createListResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const history = createListResource({
  doctype: "Dispatch Trip",
  fields: [
    "name",
    "trip_title",
    "trip_type",
    "route_assignment",
    "route_template",
    "project",
    "project.project_name as project_label",
    "shift_name",
    "trip_date",
    "status",
    "driver",
    "driver.full_name as driver_label",
    "vehicle",
    "vehicle.plate_number as vehicle_label",
  ],
  filters: { status: ["in", ["Completed", "Cancelled"]] },
  orderBy: "trip_date desc, modified desc, name desc",
  pageLength: 20,
  auto: false,
});
</script>

<template>
  <SupervisorCollection
    title="سجل الحركة"
    description="سجل زمني للرحلات المكتملة والملغاة للرجوع السريع."
    icon="clock"
    :resource="history"
    date-field="trip_date"
    :base-filters="{ status: ['in', ['Completed', 'Cancelled']] }"
    :status-options="[{ label: 'مكتملة', value: 'Completed' }, { label: 'ملغاة', value: 'Cancelled' }]"
    empty="لا توجد رحلات سابقة في السجل."
  >
    <template #default="{ rows }">
      <ol class="supervisor-history">
        <li v-for="trip in rows" :key="trip.name">
          <span class="supervisor-history__marker" aria-hidden="true" />
          <div class="supervisor-history__copy">
            <strong dir="auto">{{ recordTitle(trip, ['trip_title', 'shift_name'], 'حركة سابقة') }}</strong>
            <bdi class="record-reference" dir="auto" translate="no">{{ trip.name }}</bdi>
            <span>{{ dateTimeLabel(trip.trip_date) || 'التاريخ غير محدد' }}</span>
            <small dir="auto">{{ trip.driver_label || trip.driver || 'السائق غير مسند' }} · <bdi translate="no">{{ trip.vehicle_label || trip.vehicle || 'المركبة غير مسندة' }}</bdi></small>
          </div>
          <Badge :theme="statusTheme(trip.status)" :label="statusLabel(trip.status)" />
        </li>
      </ol>
    </template>
  </SupervisorCollection>
</template>
