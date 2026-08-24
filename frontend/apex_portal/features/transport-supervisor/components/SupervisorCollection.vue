<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, watch } from "vue";
import { Button, FormControl } from "frappe-ui";
import { Link } from "frappe-ui/frappe";
import { routeLocationKey, routerKey } from "vue-router";
import { filtersFromQuery, queryFromFilters, resultCountLabel } from "../queueState.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { __ } from "../../../core/i18n.js";

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
  liveDoctype: { type: String, default: "" },
  liveEvent: { type: String, default: "" },
});

const route = inject(routeLocationKey, reactive({ query: {} }));
const router = inject(routerKey, null);
const filters = reactive({ status: "", project: "", date: "" });
const allowedStatuses = computed(() => props.statusOptions.map((option) => option.value));

const rows = computed(() => {
  if (Array.isArray(props.resource.data)) return props.resource.data;
  for (const key of props.collections) {
    if (Array.isArray(props.resource.data?.[key])) return props.resource.data[key];
  }
  return [];
});
const loading = computed(() => props.resource.list?.loading ?? props.resource.loading);
const error = computed(() => props.resource.list?.error ?? props.resource.error);
let queryGeneration = 0;
let queryQueue = Promise.resolve();

function reloadResource() {
  return props.resource.reload?.() ?? props.resource.fetch?.();
}

// A collection that names its room re-reads itself when the room rings, keeping the filters
// and the page the supervisor is already looking at. The event is a doorbell: nothing about a
// rider crosses the socket, and the rows come back through the same permission-scoped list.
const subscribeDoctype = inject("portalDoctypeSubscribe", () => () => {});
let unsubscribe = () => {};
onMounted(() => {
  if (!props.liveDoctype || !props.liveEvent) return;
  unsubscribe = subscribeDoctype(props.liveDoctype, props.liveEvent, () => reloadResource()) || (() => {});
});
onBeforeUnmount(() => unsubscribe());

function normalizedFilters(query) {
  return {
    status: typeof query?.status === "string" && allowedStatuses.value.includes(query.status)
      ? query.status
      : "",
    project: typeof query?.project === "string" ? query.project : "",
    date: typeof query?.date === "string" ? query.date : "",
  };
}

function applyQuery(query) {
  const generation = ++queryGeneration;
  const nextFilters = normalizedFilters(query);
  queryQueue = queryQueue
    .catch(() => undefined)
    .then(async () => {
      if (generation !== queryGeneration) return;
      Object.assign(filters, nextFilters);
      props.resource.update?.({
        start: 0,
        filters: filtersFromQuery(filters, {
          base: props.baseFilters,
          dateField: props.dateField,
          allowedStatuses: allowedStatuses.value,
        }),
      });
      try {
        await reloadResource();
      } catch {
        return;
      }
    });
  return queryQueue;
}

function refresh() {
  return applyQuery(route.query || queryFromFilters(filters));
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
        <p class="feature-page__eyebrow">{{ __("Transport Operations") }}</p>
        <h2>{{ title }}</h2>
        <p>{{ description }}</p>
      </div>
      <div class="supervisor-collection__actions">
        <slot name="action" />
        <Button
          variant="outline"
          icon-left="lucide-refresh-cw"
          :loading="loading"
          @click="refresh"
        >
          {{ __("Refresh") }}
        </Button>
        <span :class="icon" aria-hidden="true" />
      </div>
    </header>

    <form class="supervisor-filters" :aria-label="__('Filter List')" @submit.prevent="updateFilters">
      <FormControl
        v-if="statusOptions.length"
        v-model="filters.status"
        type="select"
        :label="__('Status')"
        :options="[{ label: __('All Statuses'), value: '' }, ...statusOptions]"
      />
      <Link
        v-model="filters.project"
        doctype="Project"
        :label="__('Project')"
        :placeholder="__('Search for a project')"
      />
      <FormControl v-if="dateField" v-model="filters.date" type="date" :label="__('Date')" />
      <Button type="submit" variant="outline">{{ __("Apply Filters") }}</Button>
    </form>

    <PortalSkeleton v-if="loading && !resource.data" :rows="4" :label="__('Loading {0}', [title])" />
    <PortalErrorState v-else-if="error" :title="__('Could not load {0}', [title])" :message="error" @retry="refresh" />
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
        {{ __("Load More") }}
      </Button>
    </template>
  </section>
</template>
