<script setup>
import { computed } from "vue";
import { Button, ErrorMessage, LoadingIndicator } from "frappe-ui";
import { recordTitle, statusLabel } from "../../../core/displayLabels.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";

const props = defineProps({
  title: { type: String, required: true },
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: [Object, String], default: null },
  refresh: { type: Function, required: true },
  emptyText: { type: String, default: "لا توجد بيانات حالياً." },
  titleFields: { type: Array, default: () => [] },
  fallbackTitle: { type: String, default: "سجل" },
});

const titleId = computed(() => `resource-list-${props.title.replace(/\s+/g, "-")}`);
</script>

<template>
  <section class="feature-page" :aria-labelledby="titleId">
    <header class="feature-page__header">
      <h2 :id="titleId">{{ title }}</h2>
      <div class="feature-page__actions">
        <slot name="actions" />
        <Button variant="subtle" icon-left="refresh-cw" label="تحديث" :loading="loading" @click="refresh" />
      </div>
    </header>
    <LoadingIndicator v-if="loading && !rows.length" aria-label="جارٍ التحميل" />
    <PortalErrorState v-else-if="error" :title="`تعذّر تحميل ${title}`" :message="error" fallback="تعذر تحميل البيانات." @retry="refresh" />
    <p v-else-if="!rows.length" class="feature-page__empty">{{ emptyText }}</p>
    <ul v-else class="feature-page__list">
      <li v-for="(row, index) in rows" :key="row.name || index">
        <slot name="row" :row="row">
          <div class="record-identity">
            <strong dir="auto">{{ recordTitle(row, titleFields, `${fallbackTitle} ${index + 1}`) }}</strong>
            <bdi v-if="row.name" class="record-reference" dir="auto" translate="no">{{ row.name }}</bdi>
          </div>
          <small v-if="row.status">{{ statusLabel(row.status) }}</small>
        </slot>
      </li>
    </ul>
  </section>
</template>
