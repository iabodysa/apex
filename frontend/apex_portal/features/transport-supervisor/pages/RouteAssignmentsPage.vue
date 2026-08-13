<script setup>
import { Badge, FeatherIcon, createListResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const assignments = createListResource({
  doctype: "Route Assignment",
  fields: [
    "name",
    "assignment_name",
    "route_template",
    "work_shift",
    "shift_name",
    "project",
    "driver",
    "vehicle",
    "starts_on",
    "ends_on",
    "enabled",
    "route_supervisor",
    "status",
    "generated_through",
  ],
  orderBy: "modified desc, name desc",
  pageLength: 50,
  auto: false,
});
</script>

<template>
  <SupervisorCollection
    title="التشغيل المتكرر"
    description="الشفت والمسار والمشروع والإسناد الافتراضي في سجل واحد يعتمد قبل توليد الرحلات."
    icon="repeat"
    :resource="assignments"
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
            <Badge :theme="statusTheme(assignment.status)" :label="statusLabel(assignment.status)" />
          </header>
          <dl>
            <div><dt>الشفت</dt><dd dir="auto">{{ assignment.work_shift || assignment.shift_name || 'غير محدد' }}</dd></div>
            <div><dt>المسار</dt><dd dir="auto">{{ assignment.route_template || 'غير محدد' }}</dd></div>
            <div><dt>المشروع</dt><dd dir="auto">{{ assignment.project || 'غير محدد' }}</dd></div>
            <div><dt>السائق</dt><dd dir="auto">{{ assignment.driver || 'غير مسند' }}</dd></div>
            <div><dt>يبدأ في</dt><dd>{{ dateTimeLabel(assignment.starts_on) || 'غير محدد' }}</dd></div>
            <div><dt>مولّد حتى</dt><dd>{{ dateTimeLabel(assignment.generated_through) || 'لم يبدأ' }}</dd></div>
          </dl>
          <span class="supervisor-open-link">فتح التشغيل <FeatherIcon name="arrow-left" aria-hidden="true" /></span>
        </RouterLink>
      </div>
    </template>
  </SupervisorCollection>
</template>
