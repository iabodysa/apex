<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button, createResource } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { statusLabel, statusTheme, vehicleCategoryLabel } from "../../../core/displayLabels.js";
const resource = createResource({
  url: "apex.salis.api.fleet_employee.get_my_vehicle",
  method: "GET",
  auto: false,
});
const vehicle = computed(() => resource.data?.vehicle || null);
const canHandover = (globalThis.window?.apex_portal?.capabilities || []).includes("fleet.self.handover");
onMounted(() => resource.fetch());
</script>
<template>
  <section class="salis-page">
    <header class="salis-page__heading">
      <div>
        <p class="salis-eyebrow">عهدتك الحالية</p>
        <h2>المركبة</h2>
      </div>
      <Button variant="ghost" icon-left="lucide-refresh-cw" label="تحديث" @click="resource.fetch()" />
    </header>
    <AsyncPanel v-if="resource.loading" state="loading" title="جاري تحميل المركبة" message="لحظات وتظهر التفاصيل." />
    <AsyncPanel v-else-if="resource.error" state="error" title="تعذّر تحميل المركبة" :message="resource.error" @retry="resource.fetch()" />
    <AsyncPanel v-else-if="!vehicle" state="empty" title="لا توجد مركبة مسندة" message="ستظهر هنا بعد الإسناد من مشرف التشغيل." />
    <article v-else class="salis-card">
      <Badge :theme="statusTheme(vehicle.status || 'assigned')" :label="statusLabel(vehicle.status || 'assigned')" />
      <h3>
        <bdi>{{ vehicle.plate }}</bdi>
      </h3>
      <p>{{ vehicleCategoryLabel(vehicle.model) || "الفئة غير محددة" }}</p>
      <dl>
        <div>
          <dt>المشروع</dt>
          <dd>{{ vehicle.office || "—" }}</dd>
        </div>
        <div>
          <dt>قراءة العداد</dt>
          <dd>
            <bdi>{{ vehicle.odometerKm || 0 }} كم</bdi>
          </dd>
        </div>
      </dl>
      <RouterLink v-if="canHandover" class="salis-primary-link" to="/vehicle/receipt">تأكيد الاستلام</RouterLink>
      <RouterLink v-if="canHandover" to="/vehicle/return">إرجاع المركبة</RouterLink>
    </article>
  </section>
</template>
