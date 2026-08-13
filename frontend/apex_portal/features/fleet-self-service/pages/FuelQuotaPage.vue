<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button, createResource } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.get_my_fuel_quota",
  method: "GET",
  auto: false,
});
const quota = computed(() => resource.data?.quota || null);
onMounted(() => resource.fetch());
</script>
<template>
  <section class="salis-page">
    <header class="salis-page__heading">
      <div>
        <p class="salis-eyebrow">هذا الشهر</p>
        <h2>رصيد الوقود</h2>
      </div>
      <Button variant="ghost" icon-left="refresh-cw" label="تحديث" @click="resource.fetch()" />
    </header>
    <AsyncPanel v-if="resource.loading" state="loading" title="جاري تحميل الرصيد" message="نراجع الحصة والاستهلاك." />
    <AsyncPanel v-else-if="resource.error" state="error" title="تعذر تحميل الرصيد" message="حاول مرة ثانية." @retry="resource.fetch()" />
    <AsyncPanel v-else-if="!quota" state="empty" title="لا توجد حصة نشطة" message="راجع مشرف التشغيل إذا كنت تحتاج حصة وقود." />
    <article v-else class="salis-card">
      <Badge :theme="statusTheme(quota.status)" :label="statusLabel(quota.status)" />
      <div class="salis-metrics">
        <div class="salis-metric">
          <strong>
            <bdi>{{ quota.remaining_litres }} لتر</bdi>
          </strong>
          <span>المتبقي</span>
        </div>
        <div class="salis-metric">
          <strong>
            <bdi>{{ quota.monthly_litres }} لتر</bdi>
          </strong>
          <span>الحصة</span>
        </div>
      </div>
      <RouterLink class="salis-primary-link" to="/fuel/request">طلب وقود</RouterLink>
      <RouterLink to="/fuel/additional">طلب زيادة الحصة</RouterLink>
    </article>
  </section>
</template>
