<script setup>
import { computed, ref, watch } from "vue";
import { createResource } from "frappe-ui";
import { RouterLink, useRoute } from "vue-router";
import { fieldLabel, recordTitle, statusLabel } from "../../core/displayLabels.js";
import { errorStatus } from "../../core/errorMessage.js";
import PortalSkeleton from "../../components/PortalSkeleton.vue";
import PortalErrorState from "../../components/PortalErrorState.vue";
import { __ } from "../../core/i18n.js";

const route = useRoute();
let resource;
const state = ref("loading");
const data = ref(null);
const error = ref(null);

const spec = computed(() => route.meta.view || {});
const records = computed(() => {
  if (Array.isArray(data.value)) return data.value;
  for (const key of spec.value.collections || []) {
    if (Array.isArray(data.value?.[key])) return data.value[key];
  }
  return [];
});
const hasCollectionPayload = computed(() => Array.isArray(data.value) || (spec.value.collections || []).some((key) => Array.isArray(data.value?.[key])));
function valueAt(source, path) {
  return path.split(".").reduce((value, key) => value?.[key], source);
}

async function load() {
  state.value = "loading";
  error.value = null;
  try {
    if (!spec.value.endpoint) throw new Error(__("The service is not available right now."));
    if (resource?.url !== spec.value.endpoint) {
      resource = createResource({ url: spec.value.endpoint, method: "GET", auto: false });
    }
    data.value = await resource.fetch(route.params.name ? { name: route.params.name } : undefined);
    state.value = hasCollectionPayload.value ? (records.value.length ? "ready" : "empty") : data.value && Object.keys(data.value).length ? "ready" : "empty";
  } catch (reason) {
    state.value = [401, 403].includes(errorStatus(reason)) ? "denied" : "error";
    error.value = reason;
  }
}

watch(() => route.fullPath, load, { immediate: true });
</script>

<template>
  <section class="feature-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading">
      <div>
        <p class="feature-page__eyebrow">{{ spec.eyebrow }}</p>
        <h2>{{ spec.title }}</h2>
        <p>{{ spec.description }}</p>
      </div>
      <span :class="spec.icon || 'lucide-circle'" aria-hidden="true" />
    </header>

    <PortalSkeleton v-if="state === 'loading'" :rows="3" :label="__('Loading {0}', [spec.title || __('The data')])" />
    <PortalErrorState v-else-if="state === 'denied'" :title="__('Could not open the page')" :message="error" :fallback="__('You do not have permission to view this page.')" @retry="load" />
    <PortalErrorState v-else-if="state === 'error'" :title="__('Could not load the page')" :message="error" :fallback="__('Could not load the data.')" @retry="load" />
    <div v-else-if="state === 'empty'" class="feature-state">
      {{ spec.empty || __("There is no data right now.") }}
    </div>
    <div v-else class="feature-grid">
      <component :is="spec.detail ? RouterLink : 'article'" v-for="record in records" :key="record.name" class="feature-card record-card" :to="spec.detail ? spec.detail.replace(':name', record.name) : undefined">
        <div class="record-card__copy">
          <strong class="record-card__title" dir="auto">{{ recordTitle(record, spec.titleFields, spec.fallbackTitle) }}</strong>
          <bdi v-if="record.name" class="record-reference" dir="auto" translate="no">{{ record.name }}</bdi>
          <span v-if="record.description" class="record-card__description">{{ record.description }}</span>
        </div>
        <span class="record-card__meta">{{ record.status ? statusLabel(record.status) : record.trip_date || "" }}</span>
      </component>
      <dl v-if="!records.length" class="feature-details">
        <template v-for="field in spec.fields || []" :key="field.key">
          <dt>{{ field.label }}</dt>
          <dd dir="auto">{{ fieldLabel(field.key, valueAt(data, field.key)) || "—" }}</dd>
        </template>
      </dl>
    </div>
  </section>
</template>
