<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button, createResource } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { useResourceState } from "../../../core/useResourceState.js";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
const contextResource = createResource({
  url: "apex.salis.api.fleet_employee.get_context",
  method: "GET",
  auto: false,
});
const context = computed(() => contextResource.data || {});
const state = useResourceState(contextResource, () => context.value.state === "unlinked");
const grants = new Set(globalThis.window?.apex_portal?.capabilities || []);
const can = (capability) => grants.has(capability);
onMounted(() => contextResource.fetch());
</script>
<template>
  <section class="salis-page">
    <header>
      <p class="salis-eyebrow">مرحباً بك</p>
      <h2>خدمات ساليس</h2>
    </header>
    <AsyncPanel v-if="state === 'loading'" state="loading" title="جاري تجهيز حسابك" message="نتحقق من مركبتك وخدماتك." />
    <AsyncPanel v-else-if="state === 'error'" state="error" title="تعذر تجهيز الحساب" message="حاول مرة ثانية." @retry="contextResource.fetch()" />
    <AsyncPanel v-else-if="state === 'empty'" state="empty" title="حسابك غير مرتبط بمندوب" message="راجع مشرف التشغيل لربط المستخدم ببياناتك." />
    <template v-else>
      <article class="salis-card">
        <div>
          <p>المندوب</p>
          <strong>{{ context.driver_name || "—" }}</strong>
        </div>
        <Badge :theme="statusTheme(context.assignment_status || 'assigned')" :label="statusLabel(context.assignment_status || 'assigned')" />
        <p>
          المركبة:
          <bdi>{{ context.vehicle_plate || "لا توجد مركبة مسندة" }}</bdi>
        </p>
      </article>
      <div class="salis-metrics">
        <RouterLink class="salis-metric" to="/vehicle">
          <strong>مركبتي</strong>
          <span>الاستلام والإرجاع</span>
        </RouterLink>
        <RouterLink v-if="can('fleet.self.fuel')" class="salis-metric" to="/fuel">
          <strong>الوقود</strong>
          <span>الرصيد والطلبات</span>
        </RouterLink>
        <RouterLink v-if="can('fleet.self.incident')" class="salis-metric" to="/incidents">
          <strong>الحوادث</strong>
          <span>بلاغاتك السابقة</span>
        </RouterLink>
        <RouterLink v-if="can('fleet.self.complaint')" class="salis-metric" to="/complaints">
          <strong>البلاغات</strong>
          <span>المتابعة والردود</span>
        </RouterLink>
      </div>
      <Button variant="outline" icon="lucide-refresh-cw" label="تحديث" @click="contextResource.fetch()" />
    </template>
  </section>
</template>
