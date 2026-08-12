<script setup>
import { computed, inject, onMounted, ref } from "vue";
import { Badge, Button, FeatherIcon } from "frappe-ui";
import { useRoute } from "vue-router";

const route = useRoute();
const gateway = inject("transportSupervisorGateway", null);
const state = ref("loading");
const data = ref(null);
const error = ref("");
const spec = computed(() => route.meta.view || {});
const rows = computed(() => {
  if (Array.isArray(data.value)) return data.value;
  for (const key of spec.value.collections || ["items", "plans", "trips", "requests"]) if (Array.isArray(data.value?.[key])) return data.value[key];
  return [];
});

async function load() {
  state.value = "loading";
  try {
    data.value = await gateway[spec.value.gateway](route.params.name);
    state.value = rows.value.length || (data.value && Object.keys(data.value).length) ? "ready" : "empty";
  } catch (reason) {
    state.value = reason?.status === 403 ? "denied" : "error";
    error.value = reason?.message || "تعذّر تحميل لوحة التشغيل.";
  }
}
onMounted(load);
</script>

<template>
  <section class="feature-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading"><div><p class="feature-page__eyebrow">تشغيل النقل</p><h2>{{ spec.title }}</h2><p>{{ spec.description }}</p></div><FeatherIcon :name="spec.icon || 'activity'" /></header>
    <div v-if="state === 'loading'" class="feature-state" role="status">جارٍ تحديث التشغيل…</div>
    <div v-else-if="state === 'denied'" class="feature-state">لا تملك صلاحية هذا النطاق.</div>
    <div v-else-if="state === 'error'" class="feature-state feature-state--error"><p>{{ error }}</p><Button variant="outline" @click="load">إعادة المحاولة</Button></div>
    <div v-else-if="state === 'empty'" class="feature-state">{{ spec.empty || 'لا توجد عمليات في هذا النطاق.' }}</div>
    <div v-else class="feature-grid feature-grid--wide">
      <article v-for="row in rows" :key="row.name" class="feature-card">
        <div><strong>{{ row.route_name || row.subject || row.name }}</strong><span>{{ row.project || row.shift || row.trip_date }}</span></div>
        <Badge :label="row.workflow_state || row.status || 'جديد'" />
      </article>
      <dl v-if="!rows.length" class="feature-details"><template v-for="field in spec.fields || []" :key="field.key"><dt>{{ field.label }}</dt><dd dir="auto">{{ data?.[field.key] || '—' }}</dd></template></dl>
    </div>
  </section>
</template>
