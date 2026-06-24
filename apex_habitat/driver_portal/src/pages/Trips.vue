<template>
  <div class="space-y-4">
    <h2 class="section-title">{{ t("trips.title") }}</h2>

    <LoadingState v-if="trips.loading" :label="t('common.loading')" />

    <ErrorState v-else-if="trips.error" :message="t('errors.loadFailed')" @retry="trips.reload()" />

    <EmptyState
      v-else-if="!trips.data || !trips.data.length"
      icon="route"
      :title="t('trips.empty')"
      :hint="t('trips.emptyHint')"
    />

    <router-link
      v-for="t in trips.data"
      :key="t.name"
      :to="'/route/' + encodeURIComponent(t.name)"
      class="card card-pad block"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="font-bold leading-tight"><bdi>{{ t.route_plan || t.name }}</bdi></div>
        <span class="pill pill-accent shrink-0">{{ t.status }}</span>
      </div>
      <div class="mt-2 flex items-center gap-2 text-sm text-soft">
        <Icon name="truck" :size="16" class="text-primary shrink-0" />
        <span><bdi>{{ t.vehicle || "—" }}</bdi></span>
        <span class="text-muted">·</span>
        <span><bdi>{{ t.depart_time || "" }}</bdi> → <bdi>{{ t.return_time || "" }}</bdi></span>
        <Icon name="route" :size="16" class="text-primary shrink-0 ms-auto" />
      </div>
    </router-link>
  </div>
</template>

<script setup>
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const trips = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_trips_today",
  auto: true,
});
</script>
