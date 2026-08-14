<script setup>
import { Badge, createListResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusOptions, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const history = createListResource({
  doctype: "Dispatch Trip",
  fields: [
    "name",
    "trip_title",
    "trip_type",
    "route_assignment",
    "route_assignment.assignment_name as route_assignment_label",
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
    "route_template.template_name as route_template_label",
  ],
  filters: { status: ["in", ["Completed", "Cancelled"]] },
  orderBy: "trip_date desc, modified desc, name desc",
  pageLength: 20,
  auto: false,
});
const historyStatusOptions = statusOptions(["Completed", "Cancelled"]);
</script>

<template>
  <SupervisorCollection
    title="سجل الحركة"
    description="سجل زمني للرحلات المكتملة والملغاة للرجوع السريع."
    icon="clock"
    :resource="history"
    date-field="trip_date"
    :base-filters="{ status: ['in', ['Completed', 'Cancelled']] }"
    :status-options="historyStatusOptions"
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
            <small dir="auto">{{ trip.driver_label || 'السائق غير مسند' }} · <bdi translate="no">{{ trip.vehicle_label || 'المركبة غير مسندة' }}</bdi></small>
            <small v-if="trip.project_label || trip.route_template_label || trip.route_assignment_label" dir="auto">
              {{ [trip.project_label, trip.route_template_label, trip.route_assignment_label].filter(Boolean).join(' · ') }}
            </small>
          </div>
          <Badge :theme="statusTheme(trip.status)" :label="statusLabel(trip.status)" />
        </li>
      </ol>
    </template>
  </SupervisorCollection>
</template>
