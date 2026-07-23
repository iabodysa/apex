<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("accommodation.title") }}</h2>

    <!-- Stale note when rendering the last-known cached snapshot offline. -->
    <div v-if="isStale" class="stale-note">
      <Icon name="alert" :size="14" class="shrink-0" />
      <span>{{ t("common.stale") }}</span>
    </div>

    <template v-if="acc.loading && !ad">
      <Skeleton variant="stats" :lines="3" />
      <Skeleton :lines="4" />
    </template>

    <!-- Error with NO cached fallback: an invalid/disabled token (PermissionError)
         or a server failure must NOT masquerade as a benign "no assignment" empty
         state. With a cached snapshot we render it (labelled stale) instead. -->
    <div v-else-if="acc.error && !ad" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("errors.loadError") }}</p>
      <p class="text-sm text-muted">{{ errorMessage }}</p>
      <button class="btn btn-primary mt-3" style="width: auto; padding-inline: 24px" @click="acc.reload()">
        {{ t("common.retry") }}
      </button>
    </div>

    <template v-else-if="ad && ad.assignment">
      <!-- Building / room / bed -->
      <section class="card card-pad space-y-4">
        <div class="flex items-center gap-3">
          <span class="avatar h-11 w-11" style="background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary)">
            <Icon name="building" :size="22" />
          </span>
          <div class="min-w-0">
            <div class="text-base font-extrabold leading-tight truncate">
              {{ building?.building_name || ad.assignment.name }}
            </div>
            <div v-if="buildingLocation" class="text-sm text-muted truncate">{{ buildingLocation }}</div>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-3">
          <div class="stat">
            <div class="stat-label">{{ t("accommodation.room") }}</div>
            <div class="stat-value"><bdi>{{ room?.room_number || "—" }}</bdi></div>
          </div>
          <div class="stat">
            <div class="stat-label">{{ t("accommodation.bed") }}</div>
            <div class="stat-value"><bdi>{{ bed?.bed_code || "—" }}</bdi></div>
          </div>
          <div class="stat">
            <div class="stat-label">{{ t("accommodation.floor") }}</div>
            <div class="stat-value">{{ room?.floor != null ? room.floor : "—" }}</div>
          </div>
        </div>

        <dl class="space-y-3 text-sm">
          <Row icon="calendar" :label="t('accommodation.checkIn')" :value="formatDate(ad.assignment.check_in_date)" />
          <Row v-if="ad.assignment.stay_type" icon="clock" :label="t('accommodation.stayType')" :value="tEnum('stayType', ad.assignment.stay_type)" />
          <Row v-if="ad.assignment.expected_checkout_date" icon="clock" :label="t('accommodation.expectedCheckout')" :value="formatDate(ad.assignment.expected_checkout_date)" />
          <Row v-if="occupancy" icon="user" :label="t('accommodation.occupancy')" :value="occupancy" />
          <Row v-if="building?.address" icon="pin" :label="t('accommodation.address')" :value="building.address" />
        </dl>

        <a v-if="building?.google_maps_url" :href="building.google_maps_url" target="_blank" rel="noopener"
           class="link-tap text-primary text-sm inline-flex items-center gap-1">
          <Icon name="external" :size="14" class="rtl-flip" /> {{ t("common.openMap") }}
        </a>
      </section>

      <!-- In-charge contact -->
      <section v-if="building?.in_charge" class="card card-pad">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted mb-3">{{ t("accommodation.inCharge") }}</h3>
        <div class="flex items-center gap-3">
          <span class="avatar h-10 w-10" style="background: var(--c-mint); color: var(--c-ink)">
            <Icon name="user" :size="18" />
          </span>
          <div class="min-w-0">
            <div class="font-bold truncate">{{ building.in_charge.name }}</div>
            <div v-if="building.in_charge.phone" class="text-sm text-muted"><bdi>{{ building.in_charge.phone }}</bdi></div>
          </div>
        </div>
        <div v-if="building.in_charge.phone" class="grid grid-cols-2 gap-3 mt-3">
          <a :href="'tel:' + building.in_charge.phone" class="btn btn-primary" style="text-decoration: none">
            <Icon name="phone" :size="18" /> {{ t("common.call") }}
          </a>
          <a :href="waLink(building.in_charge.phone)" target="_blank" rel="noopener" class="btn btn-accent" style="text-decoration: none">
            <Icon name="message" :size="18" /> {{ t("common.whatsapp") }}
          </a>
        </div>
      </section>

      <!-- Notices -->
      <section v-if="ad.assignment.notes" class="card card-pad">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted mb-2">{{ t("accommodation.notes") }}</h3>
        <p class="text-sm text-soft whitespace-pre-line">{{ ad.assignment.notes }}</p>
      </section>

      <router-link to="/requests" class="btn btn-outline" style="text-decoration: none">
        <Icon name="plus" :size="18" /> {{ t("accommodation.reportIssue") }}
      </router-link>
    </template>

    <div v-else class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("accommodation.empty") }}</p>
      <p class="text-xs text-muted mt-1">{{ t("accommodation.emptyHint") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, h, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatDate } from "../utils/datetime";
import { TOKEN } from "../utils/token";
import { waLink } from "../utils/phone";
import { cacheGet, cacheSet } from "../utils/cache";

const { t, tEnum } = useI18n();

// Cache the last good accommodation read so an offline drop renders it
// stale-but-labelled instead of an error (mirrors the driver portal pattern).
const CACHE_KEY = "get_worker_accommodation";
const staleAcc = ref(null);
const acc = createResource({
  url: "apex.salis.api.masar.get_worker_accommodation",
  params: { token: TOKEN },
  auto: true,
  onSuccess: (r) => {
    staleAcc.value = null;
    cacheSet(CACHE_KEY, r);
  },
  onError: () => {
    const cached = cacheGet(CACHE_KEY);
    if (cached) staleAcc.value = cached;
  },
});

const errorMessage = computed(() => resourceErrorMessage(acc.error));

// Live data when present; otherwise the cached snapshot (offline). ad drives the UI.
const ad = computed(() => acc.data || staleAcc.value?.data || null);
const isStale = computed(() => !acc.data && !!staleAcc.value);

const building = computed(() => ad.value?.building);
const room = computed(() => ad.value?.room);
const bed = computed(() => ad.value?.bed);

const buildingLocation = computed(() => {
  const b = building.value;
  if (!b) return "";
  return [b.district, b.city].filter(Boolean).join(", ");
});

const occupancy = computed(() => {
  const b = building.value;
  if (!b || b.current_occupants == null) return "";
  return b.total_capacity ? `${b.current_occupants} / ${b.total_capacity}` : `${b.current_occupants}`;
});

const Row = (rprops) =>
  h("div", { class: "flex items-center gap-2" }, [
    h(Icon, { name: rprops.icon, size: 18, class: "text-primary shrink-0" }),
    h("dt", { class: "text-muted" }, rprops.label),
    // <bdi> isolates Latin/numeric values (dates, occupancy) inside the RTL row;
    // a no-op for Arabic/text values. [T-313]
    h("dd", { class: "ms-auto font-semibold" }, h("bdi", null, rprops.value || t("common.none"))),
  ]);
</script>

<style scoped>
.stale-note {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius, 12px);
  font-size: 0.8125rem;
  font-weight: 600;
  background: var(--c-warning-bg, #fef3c7);
  color: var(--c-warning, #92400e);
}
</style>
