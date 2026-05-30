<template>
  <div class="space-y-4">
    <h2 class="section-title">{{ t("trips.title") }}</h2>

    <div v-if="trips.loading" class="text-muted text-sm">{{ t("common.loading") }}</div>

    <div v-else-if="!trips.data || !trips.data.length" class="card card-pad text-center">
      <div
        class="avatar mx-auto mb-2 h-11 w-11"
        style="background: color-mix(in srgb, var(--c-mint) 25%, transparent); color: var(--c-primary)"
      >
        <Icon name="route" :size="22" />
      </div>
      <p class="font-semibold">{{ t("trips.empty") }}</p>
      <p class="text-sm text-muted">{{ t("trips.emptyHint") }}</p>
    </div>

    <div v-for="t in trips.data" :key="t.name" class="card card-pad">
      <div class="flex items-start justify-between gap-2">
        <div class="font-bold leading-tight">{{ t.route_plan || t.name }}</div>
        <span class="pill pill-accent shrink-0">{{ t.status }}</span>
      </div>
      <div class="mt-2 flex items-center gap-2 text-sm text-soft">
        <Icon name="truck" :size="16" class="text-primary shrink-0" />
        <span>{{ t.vehicle || "—" }}</span>
        <span class="text-muted">·</span>
        <span>{{ t.depart_time || "" }} → {{ t.return_time || "" }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const trips = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_trips_today",
  auto: true,
});
</script>
