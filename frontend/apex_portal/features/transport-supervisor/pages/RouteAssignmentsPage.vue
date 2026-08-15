<script setup>
import { Badge, createListResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusOptions, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const assignments = createListResource({
  doctype: "Route Assignment",
  fields: [
    "name",
    "assignment_name",
    "route_template",
    "work_shift",
    "shift_name",
    "work_shift.shift_name as work_shift_label",
    "project",
    "project.project_name as project_label",
    "driver",
    "driver.full_name as driver_label",
    "vehicle",
    "vehicle.plate_number as vehicle_label",
    "route_template.template_name as route_template_label",
    "starts_on",
    "ends_on",
    "enabled",
    "route_supervisor",
    "status",
    "generated_through",
  ],
  orderBy: "modified desc, name desc",
  pageLength: 20,
  auto: false,
});
const assignmentStatusOptions = statusOptions(["Pending", "Approved", "Rejected", "Cancelled"]);
</script>

<template>
  <SupervisorCollection
    title="التشغيل المتكرر"
    description="الشفت والمسار والمشروع والإسناد الافتراضي في سجل واحد يعتمد قبل توليد الرحلات."
    icon="lucide-repeat"
    :resource="assignments"
    date-field="starts_on"
    :status-options="assignmentStatusOptions"
    empty="لا يوجد تشغيل متكرر مسند إليك."
  >
    <template #default="{ rows }">
      <div class="supervisor-assignment-grid">
        <RouterLink
          v-for="assignment in rows"
          :key="assignment.name"
          class="supervisor-assignment-card"
          :to="`/assignments/${encodeURIComponent(assignment.name)}`"
        >
          <header>
            <div class="record-identity">
              <strong dir="auto">{{ recordTitle(assignment, ['assignment_name', 'shift_name'], 'تشغيل متكرر') }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ assignment.name }}</bdi>
            </div>
            <div class="supervisor-assignment-flags">
              <Badge :theme="statusTheme(assignment.status)" :label="statusLabel(assignment.status)" />
              <!-- An approved assignment that is switched off generates no trips, and the
                   status badge alone cannot tell that apart from one that is running. -->
              <Badge v-if="!assignment.enabled" theme="gray" label="متوقف" />
            </div>
          </header>
          <dl>
            <div><dt>الشفت</dt><dd dir="auto">{{ assignment.shift_name || assignment.work_shift_label || 'غير محدد' }}</dd></div>
            <div><dt>المسار</dt><dd dir="auto">{{ assignment.route_template_label || 'غير محدد' }}</dd></div>
            <div><dt>المشروع</dt><dd dir="auto">{{ assignment.project_label || 'غير محدد' }}</dd></div>
            <div><dt>السائق</dt><dd dir="auto">{{ assignment.driver_label || 'غير مسند' }}</dd></div>
            <div><dt>المركبة</dt><dd><bdi dir="auto">{{ assignment.vehicle_label || 'غير مسندة' }}</bdi></dd></div>
            <div><dt>يبدأ في</dt><dd>{{ dateTimeLabel(assignment.starts_on) || 'غير محدد' }}</dd></div>
            <div><dt>مولّد حتى</dt><dd>{{ dateTimeLabel(assignment.generated_through) || 'لم يبدأ' }}</dd></div>
          </dl>
          <span class="supervisor-open-link">فتح التشغيل <span class="lucide-arrow-left" aria-hidden="true" /></span>
        </RouterLink>
      </div>
    </template>
  </SupervisorCollection>
</template>
