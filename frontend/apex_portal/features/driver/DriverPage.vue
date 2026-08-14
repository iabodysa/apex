<script setup>
import { computed, ref, watch } from "vue";
import { Badge, createResource } from "frappe-ui";
import { RouterLink, useRoute } from "vue-router";
import { dateTimeLabel, recordTitle, statusLabel, statusTheme } from "../../core/displayLabels.js";
import { errorStatus } from "../../core/errorMessage.js";
import PortalSkeleton from "../../components/PortalSkeleton.vue";
import PortalErrorState from "../../components/PortalErrorState.vue";

const route = useRoute();
let resource;
const state = ref("loading");
const data = ref(null);
const error = ref(null);
const spec = computed(() => route.meta.view || {});
const rows = computed(() => {
  if (Array.isArray(data.value)) return data.value;
  for (const key of spec.value.collections || []) if (Array.isArray(data.value?.[key])) return data.value[key];
  return [];
});
// The record id a row is keyed and linked by. Masar names it after the DocType it came from —
// masar.py returns dispatch_trip for a Dispatch Trip — while the plainer endpoints return name.
// The DocType name is the contract, so this reads it and falls back rather than the reverse.
const rowId = (row) => row?.dispatch_trip || row?.name;
const hasCollectionPayload = computed(() => Array.isArray(data.value) || (spec.value.collections || []).some((key) => Array.isArray(data.value?.[key])));

async function load() {
  state.value = "loading";
  error.value = null;
  try {
    if (!spec.value.endpoint) throw new Error("الخدمة غير متاحة حالياً.");
    if (resource?.url !== spec.value.endpoint) {
      resource = createResource({ url: spec.value.endpoint, method: "GET", auto: false });
    }
    data.value = await resource.fetch();
    state.value = hasCollectionPayload.value ? (rows.value.length ? "ready" : "empty") : data.value && Object.keys(data.value).length ? "ready" : "empty";
  } catch (reason) {
    state.value = [401, 403].includes(errorStatus(reason)) ? "denied" : "error";
    error.value = reason;
  }
}

watch(() => route.fullPath, load, { immediate: true });
</script>

<template>
  <section class="feature-page" :aria-busy="state === 'loading' || state === 'saving'">
    <header class="feature-page__heading">
      <div>
        <p class="feature-page__eyebrow">مسار السائق</p>
        <h2>{{ spec.title }}</h2>
        <p>{{ spec.description }}</p>
      </div>
      <span :class="spec.icon || 'lucide-navigation'" aria-hidden="true" />
    </header>
    <PortalSkeleton v-if="state === 'loading'" :rows="3" :label="`جارٍ تحميل ${spec.title || 'البيانات'}`" />
    <PortalErrorState v-else-if="state === 'denied'" title="تعذّر فتح القسم" :message="error" fallback="هذا القسم غير متاح لحسابك." @retry="load" />
    <PortalErrorState v-else-if="state === 'error'" title="تعذّر تحميل الصفحة" :message="error" fallback="تعذّر تحميل البيانات." @retry="load" />
    <div v-else-if="state === 'empty'" class="feature-state">
      {{ spec.empty || "لا توجد بيانات حالياً." }}
    </div>
    <div v-else class="feature-grid">
      <component :is="spec.detail ? RouterLink : 'article'" v-for="row in rows" :key="rowId(row)" class="feature-card record-card" :to="spec.detail ? spec.detail.replace(':trip', rowId(row)) : undefined">
        <div class="record-card__copy">
          <strong class="record-card__title" dir="auto">{{ recordTitle(row, spec.titleFields, spec.fallbackTitle) }}</strong>
          <bdi v-if="rowId(row)" class="record-reference" dir="auto" translate="no">{{ rowId(row) }}</bdi>
          <span v-if="row.description" class="record-card__description">{{ row.description }}</span>
        </div>
        <Badge :theme="statusTheme(row.status)" :label="statusLabel(row.status || 'جاهز')" />
        <span class="record-card__meta">{{ dateTimeLabel(row.depart_time || row.trip_date) }}</span>
      </component>
      <dl v-if="!rows.length" class="feature-details">
        <template v-for="field in spec.fields || []" :key="field.key">
          <dt>{{ field.label }}</dt>
          <dd dir="auto">{{ data?.[field.key] || "—" }}</dd>
        </template>
      </dl>
    </div>
  </section>
</template>
