<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("transport.title") }}</h2>

    <div v-if="tr.loading" class="text-muted text-sm">{{ t("common.loading") }}</div>

    <template v-else-if="tr.data && tr.data.trips && tr.data.trips.length">
      <section v-for="trip in tr.data.trips" :key="trip.transport_request" class="card card-pad space-y-3">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="font-extrabold leading-tight truncate">
              {{ trip.request_type || trip.transport_request }}
            </div>
            <div v-if="trip.pickup_point || trip.pickup_datetime" class="mt-0.5 text-sm text-muted">
              <span v-if="trip.pickup_point">{{ trip.pickup_point }}</span>
              <span v-if="trip.depart_time || trip.pickup_datetime"> · {{ trip.depart_time || formatDt(trip.pickup_datetime) }}</span>
            </div>
          </div>
          <span v-if="trip.status" class="pill pill-accent shrink-0">{{ trip.status }}</span>
        </div>

        <!-- Vehicle + driver -->
        <div v-if="trip.vehicle || trip.driver" class="grid grid-cols-1 gap-3">
          <div v-if="trip.vehicle" class="flex items-center gap-2 text-sm">
            <Icon name="truck" :size="18" class="text-primary shrink-0" />
            <span class="text-muted">{{ t("transport.vehicle") }}</span>
            <span class="ms-auto font-semibold">
              {{ trip.vehicle.plate_number || trip.vehicle.name }}
              <span v-if="trip.vehicle.vehicle_category" class="text-muted font-normal">· {{ trip.vehicle.vehicle_category }}</span>
            </span>
          </div>
          <div v-if="trip.driver" class="flex items-center gap-2 text-sm">
            <Icon name="user" :size="18" class="text-primary shrink-0" />
            <span class="text-muted">{{ t("transport.driver") }}</span>
            <span class="ms-auto font-semibold">{{ trip.driver.full_name }}</span>
          </div>
          <div v-if="trip.driver && trip.driver.phone" class="grid grid-cols-2 gap-3">
            <a :href="'tel:' + trip.driver.phone" class="btn btn-primary" style="text-decoration: none">
              <Icon name="phone" :size="18" /> {{ t("common.call") }}
            </a>
            <a :href="waLink(trip.driver.phone)" target="_blank" rel="noopener" class="btn btn-accent" style="text-decoration: none">
              <Icon name="message" :size="18" /> {{ t("common.whatsapp") }}
            </a>
          </div>
        </div>

        <!-- Ordered route stops -->
        <div v-if="trip.stops && trip.stops.length">
          <div class="field-label">{{ t("transport.stops") }}</div>
          <ol class="space-y-2">
            <li v-for="(stop, i) in trip.stops" :key="i" class="flex items-start gap-3">
              <span class="avatar h-6 w-6 text-xs shrink-0"
                    style="background: var(--c-primary); color: var(--c-primary-ink); border-radius: var(--radius-sm)">
                {{ stop.sequence || i + 1 }}
              </span>
              <div class="min-w-0">
                <div class="font-semibold leading-tight">
                  {{ stop.stop_name || t("transport.stop") }}
                  <span v-if="stop.planned_time" class="text-muted font-normal">· {{ stop.planned_time }}</span>
                </div>
                <div v-if="stop.pickup" class="text-sm text-muted">
                  {{ stop.pickup.building_name || stop.accommodation_building }}
                  <span v-if="stop.pickup.city">, {{ stop.pickup.city }}</span>
                </div>
                <div v-else-if="stop.location" class="text-sm text-muted">{{ stop.location }}</div>
              </div>
            </li>
          </ol>
        </div>
      </section>

      <router-link to="/requests" class="btn btn-outline" style="text-decoration: none">
        <Icon name="plus" :size="18" /> {{ t("transport.reportIssue") }}
      </router-link>
    </template>

    <div v-else class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("transport.empty") }}</p>
      <p class="text-xs text-muted mt-1">{{ t("transport.emptyHint") }}</p>
    </div>
  </div>
</template>

<script setup>
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";
import { TOKEN } from "../token";

const { t } = useI18n();

const tr = createResource({
  url: "apex_habitat.salis.api.masar.get_worker_transport",
  params: { token: TOKEN },
  auto: true,
});

function formatDt(dt) {
  if (!dt) return "";
  // Server sends "YYYY-MM-DD HH:MM:SS"; show date + HH:MM.
  return dt.slice(0, 16).replace("T", " ");
}
function waLink(phone) {
  const digits = (phone || "").replace(/[^\d]/g, "");
  return "https://wa.me/" + digits;
}
</script>
