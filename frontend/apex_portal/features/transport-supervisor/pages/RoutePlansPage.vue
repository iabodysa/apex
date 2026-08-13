<script setup>
import { Badge, FeatherIcon, createResource } from "frappe-ui";
import { recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import SupervisorCollection from "../components/SupervisorCollection.vue";

const plans = createResource({
  url: "apex.salis.api.route_supervisor.get_route_plans",
  method: "GET",
  auto: false,
});
</script>

<template>
  <SupervisorCollection
    title="خطط المسار"
    description="المسارات المعتمدة للتشغيل وما أُسند لها من سائقين ومركبات."
    icon="map"
    :resource="plans"
    :collections="['plans']"
    empty="لا توجد خطط مسار مسندة إليك."
  >
    <template #action>
      <RouterLink class="supervisor-primary-link" to="/plans/new">
        <FeatherIcon name="plus" aria-hidden="true" />
        <span>خطة جديدة</span>
      </RouterLink>
    </template>
    <template #default="{ rows }">
      <div class="supervisor-plan-grid">
        <RouterLink
          v-for="plan in rows"
          :key="plan.name"
          class="supervisor-plan-card"
          :to="`/plans/${encodeURIComponent(plan.name)}`"
        >
          <header>
            <div class="record-identity">
              <strong dir="auto">{{ recordTitle(plan, ['route_name'], 'خطة مسار') }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ plan.name }}</bdi>
            </div>
            <Badge :theme="statusTheme(plan.status || (plan.docstatus === 1 ? 'Approved' : 'Draft'))" :label="statusLabel(plan.status || (plan.docstatus === 1 ? 'Approved' : 'Draft'))" />
          </header>
          <dl>
            <div><dt>الشفت</dt><dd dir="auto">{{ plan.shift || 'غير محدد' }}</dd></div>
            <div><dt>السائق</dt><dd dir="auto">{{ plan.driver || 'غير مسند' }}</dd></div>
            <div><dt>المركبة</dt><dd><bdi dir="auto" translate="no">{{ plan.vehicle || 'غير مسندة' }}</bdi></dd></div>
          </dl>
          <span class="supervisor-open-link">فتح الخطة <FeatherIcon name="arrow-left" aria-hidden="true" /></span>
        </RouterLink>
      </div>
    </template>
  </SupervisorCollection>
</template>
