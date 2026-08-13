<script setup>
import { computed, inject, reactive, watch } from "vue";
import { Button, FeatherIcon, FormControl } from "frappe-ui";
import { routeLocationKey, routerKey } from "vue-router";
import { filtersFromQuery, queryFromFilters, resultCountLabel } from "../queueState.js";

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, required: true },
  icon: { type: String, required: true },
  resource: { type: Object, required: true },
  collections: { type: Array, default: () => [] },
  empty: { type: String, required: true },
  baseFilters: { type: Object, default: () => ({}) },
  dateField: { type: String, default: "" },
  statusOptions: { type: Array, default: () => [] },
});

const route = inject(routeLocationKey, reactive({ query: {} }));
const router = inject(routerKey, null);
const filters = reactive({ status: "", project: "", date: "" });

const rows = computed(() => {
  if (Array.isArray(props.resource.data)) return props.resource.data;
  for (const key of props.collections) {
    if (Array.isArray(props.resource.data?.[key])) return props.resource.data[key];
  }
  return [];
});
const loading = computed(() => props.resource.list?.loading ?? props.resource.loading);
const error = computed(() => props.resource.list?.error ?? props.resource.error);

function refresh() {
  return props.resource.reload?.() ?? props.resource.fetch?.();
}

async function applyQuery(query) {
  Object.assign(filters, {
    status: typeof query?.status === "string" ? query.status : "",
    project: typeof query?.project === "string" ? query.project : "",
    date: typeof query?.date === "string" ? query.date : "",
  });
  props.resource.update?.({
    filters: filtersFromQuery(filters, {
      base: props.baseFilters,
      dateField: props.dateField,
    }),
  });
  await refresh();
}

function updateFilters() {
  const query = queryFromFilters(filters);
  if (router) return router.replace({ query });
  return applyQuery(query);
}

function loadMore() {
  return props.resource.next?.();
}

watch(() => route.query, applyQuery, { immediate: true, deep: true });
</script>

<template>
  <section class="feature-page supervisor-collection" :aria-busy="loading">
    <header class="feature-page__heading supervisor-collection__heading">
      <div>
        <p class="feature-page__eyebrow">تشغيل النقل</p>
        <h2>{{ title }}</h2>
        <p>{{ description }}</p>
      </div>
      <div class="supervisor-collection__actions">
        <slot name="action" />
        <Button
          variant="outline"
          icon-left="refresh-cw"
          :loading="loading"
          @click="refresh"
        >
          تحديث
        </Button>
        <FeatherIcon :name="icon" aria-hidden="true" />
      </div>
    </header>

    <form class="supervisor-filters" aria-label="تصفية القائمة" @submit.prevent="updateFilters">
      <FormControl
        v-if="statusOptions.length"
        v-model="filters.status"
        type="select"
        label="الحالة"
        :options="[{ label: 'كل الحالات', value: '' }, ...statusOptions]"
      />
      <FormControl v-model="filters.project" label="المشروع" />
      <FormControl v-if="dateField" v-model="filters.date" type="date" label="التاريخ" />
      <Button type="submit" variant="outline">تطبيق</Button>
    </form>

    <div v-if="loading && !resource.data" class="feature-state" role="status">
      جارٍ تحميل {{ title }}…
    </div>
    <div v-else-if="error" class="feature-state feature-state--error">
      <p role="alert">تعذّر تحميل {{ title }}.</p>
      <Button variant="outline" @click="refresh">إعادة المحاولة</Button>
    </div>
    <div v-else-if="!rows.length" class="feature-state">{{ empty }}</div>
    <template v-else>
      <p class="supervisor-result-count" role="status">{{ resultCountLabel(rows.length, resource.hasNextPage) }}</p>
      <slot :rows="rows" :data="resource.data" />
      <Button
        v-if="resource.hasNextPage"
        class="supervisor-load-more"
        variant="outline"
        :loading="loading"
        @click="loadMore"
      >
        تحميل المزيد
      </Button>
    </template>
  </section>
</template>
