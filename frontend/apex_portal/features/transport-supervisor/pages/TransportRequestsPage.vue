<script setup>
import { Badge, createResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const requests = createResource({
  url: "apex.salis.api.route_supervisor.get_transport_requests",
  method: "GET",
  auto: false,
});
</script>

<template>
  <SupervisorCollection
    title="طلبات النقل"
    description="طلبات العاملين مرتبة لتحديد الرحلة التالية ومتابعة حالتها."
    icon="inbox"
    :resource="requests"
    :collections="['requests']"
    empty="لا توجد طلبات نقل تحتاج متابعة."
  >
    <template #default="{ rows }">
      <ol class="supervisor-request-queue">
        <li v-for="(request, index) in rows" :key="request.name" class="supervisor-request-card">
          <span class="supervisor-sequence"><bdi>{{ String(index + 1).padStart(2, '0') }}</bdi></span>
          <div class="supervisor-request-card__copy">
            <strong dir="auto">{{ recordTitle(request, ['display_title'], 'طلب نقل') }}</strong>
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
            </div>
          </div>
          <Badge :theme="statusTheme(request.status)" :label="statusLabel(request.status)" />
        </li>
      </ol>
    </template>
  </SupervisorCollection>
</template>
