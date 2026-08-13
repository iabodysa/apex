<script setup>
import { Badge, createListResource } from "frappe-ui";
import { dateTimeLabel, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const requests = createListResource({
  doctype: "Transport Request",
  fields: [
    "name",
    "requester_name",
    "request_type",
    "service_line",
    "project",
    "from_location",
    "to_location",
    "pickup_datetime",
    "worker_count",
    "status",
    "assigned_to_trip",
  ],
  orderBy: "modified desc, name desc",
  pageLength: 50,
  auto: false,
});

function requestTitle(request) {
  if (request.from_location && request.to_location) {
    return `${request.from_location} إلى ${request.to_location}`;
  }
  return request.from_location || request.to_location || request.requester_name || "طلب نقل";
}
</script>

<template>
  <SupervisorCollection
    title="طلبات النقل"
    description="طلبات العاملين مرتبة لتحديد الرحلة التالية ومتابعة حالتها."
    icon="inbox"
    :resource="requests"
    empty="لا توجد طلبات نقل تحتاج متابعة."
  >
    <template #default="{ rows }">
      <ol class="supervisor-request-queue">
        <li v-for="(request, index) in rows" :key="request.name" class="supervisor-request-card">
          <span class="supervisor-sequence"><bdi>{{ String(index + 1).padStart(2, '0') }}</bdi></span>
          <div class="supervisor-request-card__copy">
            <strong dir="auto">{{ requestTitle(request) }}</strong>
            <bdi class="record-reference" dir="auto" translate="no">{{ request.name }}</bdi>
            <div class="supervisor-route-line">
              <span dir="auto">{{ request.from_location || 'موقع الانطلاق غير محدد' }}</span>
              <span aria-hidden="true">←</span>
              <span dir="auto">{{ request.to_location || 'الوجهة غير محددة' }}</span>
            </div>
            <div class="supervisor-meta-line">
              <span>{{ dateTimeLabel(request.pickup_datetime) || 'الموعد يحدد لاحقاً' }}</span>
              <span v-if="request.worker_count"><bdi>{{ request.worker_count }}</bdi> عامل</span>
              <span v-if="request.project_label || request.project" dir="auto">{{ request.project_label || request.project }}</span>
              <span v-if="request.assigned_to_trip" dir="auto">ضمن {{ request.assigned_to_trip }}</span>
            </div>
          </div>
          <Badge :theme="statusTheme(request.status)" :label="statusLabel(request.status)" />
        </li>
      </ol>
    </template>
  </SupervisorCollection>
</template>
