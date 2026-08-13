<script setup>
import { Badge, FeatherIcon, createListResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const trips = createListResource({
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
    "planned_start",
    "status",
    "driver",
    "driver.full_name as driver_label",
    "vehicle",
    "vehicle.plate_number as vehicle_label",
    "route_template.template_name as route_template_label",
  ],
  orderBy: "trip_date desc, modified desc, name desc",
  filters: { status: ["not in", ["Completed", "Cancelled"]] },
  pageLength: 20,
  auto: false,
});
</script>

<template>
  <SupervisorCollection
    title="الرحلات"
    description="رحلات التشغيل الحالية مع السائق والمركبة وحالة التنفيذ."
    icon="navigation"
    :resource="trips"
    date-field="trip_date"
    :base-filters="{ status: ['not in', ['Completed', 'Cancelled']] }"
    :status-options="[{ label: 'مخططة', value: 'Planned' }, { label: 'في الطريق', value: 'Dispatched' }]"
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
              <strong dir="auto">{{ recordTitle(trip, ['trip_title', 'shift_name'], 'رحلة تشغيل') }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ trip.name }}</bdi>
              <span dir="auto">{{ trip.driver_label || 'السائق غير مسند' }} · <bdi translate="no">{{ trip.vehicle_label || 'المركبة غير مسندة' }}</bdi></span>
              <small v-if="trip.project_label || trip.route_template_label || trip.route_assignment_label" dir="auto">
                {{ [trip.project_label, trip.route_template_label, trip.route_assignment_label].filter(Boolean).join(' · ') }}
              </small>
            </div>
            <Badge :theme="statusTheme(trip.status)" :label="statusLabel(trip.status)" />
            <FeatherIcon class="supervisor-row-chevron" name="arrow-left" aria-hidden="true" />
          </RouterLink>
        </li>
      </ol>
    </template>
  </SupervisorCollection>
</template>
