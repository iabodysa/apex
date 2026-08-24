<script setup>
import { Badge, createListResource } from "frappe-ui";
import { dateTimeLabel, recordTitle, statusLabel, statusOptions, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";
import { __ } from "../../../core/i18n.js";

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
    :title="__('Recurring Operations')"
    :description="__('The shift, route, project, and default assignment in one record approved before generating trips.')"
    icon="lucide-repeat"
    :resource="assignments"
    date-field="starts_on"
    :status-options="assignmentStatusOptions"
    :empty="__('No recurring operation assigned to you.')"
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
              <strong dir="auto">{{ recordTitle(assignment, ['assignment_name', 'shift_name'], __('recurring operation')) }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ assignment.name }}</bdi>
            </div>
            <div class="supervisor-assignment-flags">
              <Badge :theme="statusTheme(assignment.status)" :label="statusLabel(assignment.status)" />
              <!-- An approved assignment that is switched off generates no trips, and the
                   status badge alone cannot tell that apart from one that is running. -->
              <Badge v-if="!assignment.enabled" theme="gray" :label="__('Stopped')" />
            </div>
          </header>
          <dl>
            <div><dt>{{ __("Duty Shift") }}</dt><dd dir="auto">{{ assignment.shift_name || assignment.work_shift_label || __("Unspecified") }}</dd></div>
            <div><dt>{{ __("Route") }}</dt><dd dir="auto">{{ assignment.route_template_label || __("Unspecified") }}</dd></div>
            <div><dt>{{ __("Project") }}</dt><dd dir="auto">{{ assignment.project_label || __("Unspecified") }}</dd></div>
            <div><dt>{{ __("driver") }}</dt><dd dir="auto">{{ assignment.driver_label || __("Not Assigned") }}</dd></div>
            <div><dt>{{ __("vehicle") }}</dt><dd><bdi dir="auto">{{ assignment.vehicle_label || __("Unassigned Vehicle") }}</bdi></dd></div>
            <div><dt>{{ __("Starts On") }}</dt><dd>{{ dateTimeLabel(assignment.starts_on) || __("Unspecified") }}</dd></div>
            <div><dt>{{ __("Generated Up To") }}</dt><dd>{{ dateTimeLabel(assignment.generated_through) || __("Not Started") }}</dd></div>
          </dl>
          <span class="supervisor-open-link">{{ __("Open Operation") }} <span class="lucide-arrow-left" aria-hidden="true" /></span>
        </RouterLink>
      </div>
    </template>
  </SupervisorCollection>
</template>
