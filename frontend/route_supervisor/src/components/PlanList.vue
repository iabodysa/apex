<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <aside class="plans">
    <div class="plans-head">
      <h2 class="plans-title">{{ t("header.plans") }}</h2>
    </div>

    <div v-if="loadState === 'loading'" class="plan-skel" aria-hidden="true">
      <div v-for="n in 4" :key="n" class="skeleton-card" />
    </div>

    <LoadError
      v-else-if="loadState === 'error'"
      :title="t('list.loadError')"
      :detail="loadError"
      :hint="t('list.loadErrorHint')"
      :retry-label="t('common.retry')"
      @retry="load()"
    />

    <EmptyState v-else-if="!plans.length" :title="t('list.empty')" :hint="t('list.emptyHint')">
      <template #icon><Icon name="clipboard-check" :size="20" :stroke-width="1.6" /></template>
    </EmptyState>

    <ul v-else class="plan-list">
      <li v-for="p in plans" :key="p.name">
        <router-link
          class="plan-card"
          :class="{ sel: p.name === selectedName }"
          :to="{ name: 'plan', params: { name: p.name, tab: 'approval' } }"
          :aria-current="p.name === selectedName ? 'true' : undefined"
        >
          <span class="pc-top">
            <span class="pc-name">{{ p.route_name || p.name }}</span>
            <Badge :theme="badgeTheme(p.approval)" size="sm" :label="t('approval.' + p.approval)" />
          </span>
          <span class="pc-meta">
            <span v-if="p.project"><Icon name="badge" :size="12" /> {{ p.project }}</span>
            <span v-if="p.shift"><Icon name="clock" :size="12" /> {{ t("shift." + p.shift) }}</span>
            <span><Icon name="pin" :size="12" /> {{ t("list.stops", { n: p.total_stops }) }}</span>
            <span v-if="p.driver"><Icon name="user" :size="12" /> {{ p.driver }}</span>
            <span v-if="p.vehicle"><Icon name="truck" :size="12" /> {{ p.vehicle }}</span>
          </span>
          <span v-if="p.trip" class="pc-boarding">
            <Progress :value="pct(p.trip.boarding.boarded, p.trip.boarding.expected)" size="sm" />
            <span class="pc-bnum">
              {{ p.trip.boarding.boarded }}/{{ p.trip.boarding.expected || t("common.none") }}
            </span>
          </span>
        </router-link>
      </li>
    </ul>
  </aside>
</template>

<script setup>
import { Badge, Progress } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";

import Icon from "../Icon.vue";
import { pct } from "../fmt.js";
import { usePlans } from "../usePlans.js";
import { useI18n } from "@/i18n";

defineProps({
  selectedName: { type: String, default: "" },
});

const { t } = useI18n();
const { plans, loadState, loadError, load } = usePlans();

/* Colour never carries the state on its own — the badge always shows the word too. */
const badgeTheme = (approval) =>
  ({ Pending: "orange", Approved: "green", Rejected: "red" })[approval] || "gray";
</script>
