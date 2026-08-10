<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <HousingNav />
    <template v-if="acc.loading && !ad">
      <Skeleton variant="stats" :lines="3" />
      <Skeleton :lines="4" />
    </template>

    <LoadError
      v-else-if="acc.error && !ad"
      :title="t('errors.loadError')"
      :detail="errorMessage"
      :hint="t('errors.retryHint')"
      :retry-label="t('common.retry')"
      @retry="acc.reload()"
    />

    <template v-else-if="ad && ad.assignment">
      <section class="card card-pad space-y-4">
        <div class="flex items-center gap-3">
          <span class="avatar h-11 w-11" style="background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary)">
            <Icon name="building" :size="22" />
          </span>
          <div class="min-w-0">
            <div class="text-base font-bold leading-tight truncate">
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

      <Panel v-if="building?.in_charge" :title="t('accommodation.inCharge')">
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
      </Panel>

      <Panel v-if="ad.assignment.notes" :title="t('accommodation.notes')">
        <p class="text-sm text-soft whitespace-pre-line">{{ ad.assignment.notes }}</p>
      </Panel>

      <ActionDock>
        <template #primary>
          <router-link to="/requests" class="btn btn-outline" style="text-decoration: none">
            <Icon name="plus" :size="18" /> {{ t("accommodation.reportIssue") }}
          </router-link>
        </template>
      </ActionDock>
    </template>

    <EmptyState v-else :title="t('accommodation.empty')" :hint="t('accommodation.emptyHint')">
      <template #icon><Icon name="building" :size="22" /></template>
    </EmptyState>
  </div>
</template>

<script setup>
import { computed, h } from "vue";
import { createResource } from "frappe-ui";
import ActionDock from "@shared/components/ActionDock.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import Panel from "@shared/components/Panel.vue";
import Icon from "../components/Icon.vue";
import HousingNav from "../components/HousingNav.vue";
import Skeleton from "../components/Skeleton.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatDate } from "../utils/datetime";
import { waLink } from "../utils/phone";

const { t, tEnum } = useI18n();

const acc = createResource({
  url: "apex.salis.api.masar.get_worker_accommodation",
  auto: true,
});

const errorMessage = computed(() => resourceErrorMessage(acc.error));

const ad = computed(() => acc.data || null);

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
    h("dd", { class: "ms-auto font-semibold" }, h("bdi", null, rprops.value || t("common.none"))),
  ]);
</script>
