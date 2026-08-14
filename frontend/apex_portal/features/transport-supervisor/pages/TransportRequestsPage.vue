<script setup>
import { Badge, createListResource } from "frappe-ui";
import { dateTimeLabel, humanLabel, statusLabel, statusOptions, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const requests = createListResource({
  doctype: "Transport Request",
  fields: [
    "name",
    "requester_name",
    "requested_by",
    "requested_by.full_name as requester_label",
    "request_type",
    "service_line",
    "project",
    "project.project_name as project_label",
    "accommodation_building",
    "accommodation_building.building_name as accommodation_building_label",
    "representative",
    "representative.employee_name as representative_label",
    "destination",
    "from_location",
    "to_location",
    "pickup_datetime",
    "worker_count",
    "status",
    "assigned_to_trip",
    "assigned_to_trip.trip_title as assigned_trip_label",
    "assigned_driver",
    "assigned_driver.full_name as assigned_driver_label",
    "assigned_vehicle",
    "assigned_vehicle.plate_number as assigned_vehicle_label",
  ],
  orderBy: "modified desc, name desc",
  pageLength: 20,
  auto: false,
});

function requestTitle(request) {
  const from = request.from_location || humanLabel(request, "accommodation_building", "accommodation_building_label");
  const to = request.to_location || request.destination;
  if (from && to) {
    return `${from} إلى ${to}`;
  }
  if (request.service_line === "Administrative Trip") {
    return to ? `رحلة إدارية إلى ${to}` : `رحلة إدارية لـ ${request.representative_label || request.requester_label || request.requester_name || "ممثل"}`;
  }
  return to || from || request.request_type || request.service_line || "طلب نقل";
}

const requestStatusOptions = statusOptions([
  "New", "Validated", "Approved", "Scheduled", "Fulfilled", "Rejected", "Cancelled",
]);
</script>

<template>
  <SupervisorCollection
    title="طلبات النقل"
    description="طلبات العاملين مرتبة لتحديد الرحلة التالية ومتابعة حالتها."
    icon="inbox"
    :resource="requests"
    date-field="pickup_datetime"
    :status-options="requestStatusOptions"
    empty="لا توجد طلبات نقل تحتاج متابعة."
  >
    <template #default="{ rows }">
      <ol class="supervisor-request-queue">
        <li v-for="(request, index) in rows" :key="request.name" class="supervisor-request-card">
          <span class="supervisor-sequence"><bdi>{{ String(index + 1).padStart(2, '0') }}</bdi></span>
          <RouterLink class="supervisor-request-card__copy" :to="`/requests/${encodeURIComponent(request.name)}`">
            <strong dir="auto">{{ requestTitle(request) }}</strong>
            <bdi class="record-reference" dir="auto" translate="no">{{ request.name }}</bdi>
            <div class="supervisor-route-line">
              <span dir="auto">{{ request.from_location || request.accommodation_building_label || 'موقع الانطلاق غير محدد' }}</span>
              <span aria-hidden="true">←</span>
              <span dir="auto">{{ request.to_location || 'الوجهة غير محددة' }}</span>
            </div>
            <div class="supervisor-meta-line">
              <span v-if="request.requester_label || request.requester_name" dir="auto">{{ request.requester_label || request.requester_name }}</span>
              <span>{{ dateTimeLabel(request.pickup_datetime) || 'الموعد يحدد لاحقاً' }}</span>
              <span v-if="request.worker_count"><bdi>{{ request.worker_count }}</bdi> عامل</span>
              <span v-if="request.project_label" dir="auto">{{ request.project_label }}</span>
              <span v-if="request.assigned_to_trip" class="record-identity" dir="auto">
                ضمن {{ request.assigned_trip_label || 'رحلة مسندة' }}
                <bdi class="record-reference" translate="no">{{ request.assigned_to_trip }}</bdi>
              </span>
              <span v-if="request.assigned_driver_label" dir="auto">{{ request.assigned_driver_label }}</span>
              <bdi v-if="request.assigned_vehicle_label" translate="no">{{ request.assigned_vehicle_label }}</bdi>
            </div>
          </RouterLink>
          <Badge :theme="statusTheme(request.status)" :label="statusLabel(request.status)" />
        </li>
      </ol>
    </template>
  </SupervisorCollection>
</template>
