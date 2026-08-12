<script setup>
import { computed, inject, onMounted, ref } from "vue";
import { Button, FeatherIcon } from "frappe-ui";
import { useRoute } from "vue-router";

const route = useRoute();
const gateway = inject("workerGateway", null);
const state = ref("loading");
const data = ref(null);
const error = ref("");

const spec = computed(() => route.meta.view || {});
const records = computed(() => {
  if (Array.isArray(data.value)) return data.value;
  for (const key of spec.value.collections || []) {
    if (Array.isArray(data.value?.[key])) return data.value[key];
  }
  return [];
});
function valueAt(source, path) {
  return path.split(".").reduce((value, key) => value?.[key], source);
}

async function load() {
  state.value = "loading";
  error.value = "";
  try {
    const method = gateway?.[spec.value.gateway];
    if (!method) throw new Error("الخدمة غير متاحة حالياً.");
    data.value = await method(route.params.name);
    state.value = records.value.length || (data.value && Object.keys(data.value).length) ? "ready" : "empty";
  } catch (reason) {
    state.value = reason?.status === 403 ? "denied" : "error";
    error.value = reason?.message || "تعذّر تحميل البيانات.";
  }
}

onMounted(load);
</script>

<template>
  <section class="feature-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading">
      <div>
        <p class="feature-page__eyebrow">{{ spec.eyebrow }}</p>
        <h2>{{ spec.title }}</h2>
        <p>{{ spec.description }}</p>
      </div>
      <FeatherIcon :name="spec.icon || 'circle'" aria-hidden="true" />
    </header>

    <div v-if="state === 'loading'" class="feature-state" role="status">جارٍ التحميل…</div>
    <div v-else-if="state === 'denied'" class="feature-state">لا تملك صلاحية عرض هذه الصفحة.</div>
    <div v-else-if="state === 'error'" class="feature-state feature-state--error">
      <p>{{ error }}</p><Button variant="outline" @click="load">إعادة المحاولة</Button>
    </div>
    <div v-else-if="state === 'empty'" class="feature-state">{{ spec.empty || 'لا توجد بيانات حالياً.' }}</div>
    <div v-else class="feature-grid">
      <article v-for="record in records" :key="record.name" class="feature-card">
        <strong>{{ record.title || record.subject || record.route_name || record.name }}</strong>
        <span>{{ record.status || record.trip_date || record.description }}</span>
      </article>
      <dl v-if="!records.length" class="feature-details">
        <template v-for="field in spec.fields || []" :key="field.key">
          <dt>{{ field.label }}</dt><dd dir="auto">{{ valueAt(data, field.key) || '—' }}</dd>
        </template>
      </dl>
    </div>
  </section>
</template>
