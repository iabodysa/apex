<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("vehicle.title") }}</h2>

    <div v-if="vehicle.loading" class="text-muted text-sm">{{ t("common.loading") }}</div>

    <template v-else-if="v">
      <section class="card card-pad">
        <div class="flex items-center gap-3">
          <span
            class="avatar h-12 w-12"
            style="border-radius: var(--radius); background: var(--c-ink); color: var(--c-surface)"
          >
            <Icon name="truck" :size="26" />
          </span>
          <div class="min-w-0">
            <div class="text-lg font-extrabold leading-tight truncate">
              {{ v.plate_number || v.name }}
            </div>
            <span class="pill mt-1" :class="statusPill">{{ v.status || t("common.none") }}</span>
          </div>
        </div>

        <div class="divider my-4"></div>

        <dl class="space-y-3 text-sm">
          <div v-if="v.vehicle_category" class="flex items-center gap-2">
            <Icon name="layers" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.category") }}</dt>
            <dd class="ms-auto font-semibold">{{ v.vehicle_category }}</dd>
          </div>
          <div v-if="v.ownership" class="flex items-center gap-2">
            <Icon name="badge" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.ownership") }}</dt>
            <dd class="ms-auto font-semibold">{{ v.ownership }}</dd>
          </div>
          <div v-if="v.project" class="flex items-center gap-2">
            <Icon name="briefcase" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.project") }}</dt>
            <dd class="ms-auto font-semibold">{{ v.project }}</dd>
          </div>
          <div v-if="v.assignment_start" class="flex items-center gap-2">
            <Icon name="calendar" :size="18" class="text-primary shrink-0" />
            <dt class="text-muted">{{ t("vehicle.assignmentStart") }}</dt>
            <dd class="ms-auto font-semibold">{{ v.assignment_start }}</dd>
          </div>
        </dl>
      </section>
    </template>

    <div v-else class="card card-pad text-center">
      <div
        class="avatar mx-auto mb-2 h-11 w-11"
        style="background: color-mix(in srgb, var(--c-mint) 25%, transparent); color: var(--c-primary)"
      >
        <Icon name="truck" :size="22" />
      </div>
      <p class="font-semibold">{{ t("vehicle.empty") }}</p>
      <p class="text-sm text-muted">{{ t("vehicle.emptyHint") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const vehicle = createResource({
  url: "apex_habitat.salis.api.driver_portal.get_my_vehicle",
  auto: true,
});

const v = computed(() => vehicle.data?.vehicle || null);

const statusPill = computed(() => {
  const s = (v.value?.status || "").toLowerCase();
  if (s === "active") return "pill-success";
  if (s === "released" || s === "stopped") return "pill-danger";
  if (s === "under maintenance") return "pill-warning";
  return "pill-neutral";
});
</script>
