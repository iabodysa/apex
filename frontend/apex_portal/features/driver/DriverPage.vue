<script setup>
import { computed, inject, onMounted, ref } from "vue";
import { Button, Badge, FeatherIcon } from "frappe-ui";
import { useRoute } from "vue-router";

const route = useRoute();
const gateway = inject("driverGateway", null);
const state = ref("loading");
const data = ref(null);
const error = ref("");
const spec = computed(() => route.meta.view || {});
const rows = computed(() => {
  if (Array.isArray(data.value)) return data.value;
  for (const key of spec.value.collections || []) if (Array.isArray(data.value?.[key])) return data.value[key];
  return [];
});

async function load() {
  state.value = "loading";
  try {
    data.value = await gateway[spec.value.gateway](route.params.trip);
    state.value = rows.value.length || (data.value && Object.keys(data.value).length) ? "ready" : "empty";
  } catch (reason) {
    state.value = reason?.status === 403 ? "denied" : "error";
    error.value = reason?.message || "تعذّر تحميل البيانات.";
  }
}

async function execute(action) {
  state.value = "saving";
  try { await gateway[action](route.params.trip); await load(); }
  catch (reason) { state.value = "error"; error.value = reason?.message || "تعذّر تنفيذ الإجراء."; }
}
onMounted(load);
</script>

<template>
  <section class="feature-page" :aria-busy="state === 'loading' || state === 'saving'">
    <header class="feature-page__heading"><div><p class="feature-page__eyebrow">مسار السائق</p><h2>{{ spec.title }}</h2><p>{{ spec.description }}</p></div><FeatherIcon :name="spec.icon || 'navigation'" /></header>
    <div v-if="state === 'loading'" class="feature-state" role="status">جارٍ التحميل…</div>
    <div v-else-if="state === 'denied'" class="feature-state">هذا القسم غير متاح لحسابك.</div>
    <div v-else-if="state === 'error'" class="feature-state feature-state--error"><p>{{ error }}</p><Button variant="outline" @click="load">إعادة المحاولة</Button></div>
    <div v-else-if="state === 'empty'" class="feature-state">{{ spec.empty || 'لا توجد بيانات حالياً.' }}</div>
    <div v-else class="feature-grid">
      <article v-for="row in rows" :key="row.name" class="feature-card">
        <strong>{{ row.route_name || row.employee_name || row.name }}</strong><Badge :label="row.status || 'جاهز'" />
        <span>{{ row.depart_time || row.trip_date || row.description }}</span>
      </article>
      <dl v-if="!rows.length" class="feature-details"><template v-for="field in spec.fields || []" :key="field.key"><dt>{{ field.label }}</dt><dd dir="auto">{{ data?.[field.key] || '—' }}</dd></template></dl>
      <div v-if="spec.execution" class="feature-actions"><Button variant="solid" @click="execute('startTrip')">بدء الرحلة</Button><Button variant="outline" @click="execute('finishTrip')">إنهاء مسار السائق</Button></div>
    </div>
  </section>
</template>
