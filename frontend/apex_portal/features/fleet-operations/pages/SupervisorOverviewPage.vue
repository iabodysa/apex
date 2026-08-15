<script setup>
import { computed, onMounted } from "vue";
import { Button, createResource } from "frappe-ui";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
const r = createResource({
    url: "apex.salis.api.fleet_os.get_operations_overview",
    method: "GET",
    auto: false,
  }),
  summary = computed(() => r.data?.summary || {});
onMounted(() => r.fetch());
</script>
<template>
  <section class="ops-page">
    <header class="ops-heading">
      <div>
        <p>تشغيل ساليس</p>
        <h2>نظرة عامة</h2>
      </div>
      <Button variant="outline" icon="lucide-refresh-cw" label="تحديث" :loading="r.loading" @click="r.fetch()" />
    </header>
    <PortalSkeleton v-if="r.loading" :rows="3" label="جارٍ تحميل مؤشرات التشغيل" />
    <PortalErrorState v-else-if="r.error" title="تعذّر تحميل المؤشرات" :message="r.error" @retry="r.fetch()" />
    <div v-else class="ops-metrics">
      <RouterLink
        v-for="item in [
          { key: 'vehicles', label: 'المركبات', to: '/vehicles' },
          { key: 'assignments', label: 'الإسناد', to: '/assignments' },
          { key: 'fuel_pending', label: 'طلبات الوقود', to: '/fuel-approvals' },
          { key: 'incidents_open', label: 'الحوادث المفتوحة', to: '/incidents' },
        ]"
        :key="item.key"
        class="ops-metric"
        :to="item.to"
      >
        <strong>
          <bdi>{{ summary[item.key] || 0 }}</bdi>
        </strong>
        <span>{{ item.label }}</span>
      </RouterLink>
    </div>
  </section>
</template>
