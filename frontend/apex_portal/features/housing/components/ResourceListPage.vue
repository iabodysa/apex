<script setup>
import { computed, onMounted, watch } from "vue";
import { Button, ErrorMessage, LoadingIndicator, createResource } from "frappe-ui";

const props = defineProps({
  title: { type: String, required: true },
  endpoint: { type: String, required: true },
  params: { type: Object, default: () => ({}) },
  rowsKey: { type: String, default: "" },
  emptyText: { type: String, default: "لا توجد بيانات حالياً." },
});

const resource = createResource({ url: props.endpoint, makeParams: () => props.params });
const titleId = computed(() => `${props.endpoint.replace(/[^a-z0-9]+/gi, "-")}-title`);
const rows = computed(() => {
  const data = resource.data;
  if (Array.isArray(data)) return data;
  if (props.rowsKey && Array.isArray(data?.[props.rowsKey])) return data[props.rowsKey];
  return data ? [data] : [];
});
onMounted(() => resource.fetch());
watch(() => props.params, () => resource.fetch(), { deep: true });
</script>

<template>
  <section class="feature-page" :aria-labelledby="titleId">
    <header class="feature-page__header">
      <h2 :id="titleId">{{ title }}</h2>
      <Button variant="subtle" icon="refresh-cw" label="تحديث" :loading="resource.loading" @click="resource.fetch()" />
    </header>
    <LoadingIndicator v-if="resource.loading && !rows.length" aria-label="جارٍ التحميل" />
    <ErrorMessage v-else-if="resource.error" :message="resource.error.message || 'تعذر تحميل البيانات.'" />
    <p v-else-if="!rows.length" class="feature-page__empty">{{ emptyText }}</p>
    <ul v-else class="feature-page__list">
      <li v-for="(row, index) in rows" :key="row.name || index">
        <slot name="row" :row="row">
          <strong dir="auto">{{ row.title || row.label || row.name || `السجل ${index + 1}` }}</strong>
          <small v-if="row.status">{{ row.status }}</small>
        </slot>
      </li>
    </ul>
  </section>
</template>
