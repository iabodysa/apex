<script setup>
import { Badge, createListResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusOptions, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";
import { __ } from "../../../core/i18n.js";

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
const tripStatusOptions = statusOptions(["Planned", "Dispatched"]);
</script>

<template>
  <SupervisorCollection
    :title="__('Trips')"
    :description="__('Current operating trips with the driver, vehicle, and execution status.')"
    icon="lucide-navigation"
    :resource="trips"
    date-field="trip_date"
    :base-filters="{ status: ['not in', ['Completed', 'Cancelled']] }"
    :status-options="tripStatusOptions"
    :empty="__('No operating trips right now.')"
    live-doctype="Dispatch Trip"
    live-event="driver_trip_update"
  >
    <template #default="{ rows }">
      <ol class="supervisor-trip-board">
        <li v-for="trip in rows" :key="trip.name">
          <RouterLink :to="`/trips/${encodeURIComponent(trip.name)}`">
            <div class="supervisor-trip-date">
              <span>{{ __("Trip Time") }}</span>
              <strong><bdi>{{ dateTimeLabel(trip.trip_date) || __("Unspecified") }}</bdi></strong>
            </div>
            <div class="record-identity">
              <strong dir="auto">{{ recordTitle(trip, ['trip_title', 'shift_name'], __('Operational Trip')) }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ trip.name }}</bdi>
              <span dir="auto">{{ trip.driver_label || __("Driver Not Assigned") }} · <bdi translate="no">{{ trip.vehicle_label || __("Vehicle Not Assigned") }}</bdi></span>
              <small v-if="trip.project_label || trip.route_template_label || trip.route_assignment_label" dir="auto">
                {{ [trip.project_label, trip.route_template_label, trip.route_assignment_label].filter(Boolean).join(' · ') }}
              </small>
            </div>
            <Badge :theme="statusTheme(trip.status)" :label="statusLabel(trip.status)" />
            <span class="supervisor-row-chevron lucide-arrow-left" aria-hidden="true" />
          </RouterLink>
        </li>
      </ol>
    </template>
  </SupervisorCollection>
</template>
