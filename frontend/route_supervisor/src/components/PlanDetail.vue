<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="hero">
    <router-link v-if="narrow" to="/" class="back-btn" :aria-label="t('nav.plans')">
      <Icon name="chevron" :size="18" />
    </router-link>
    <div class="hero-main">
      <h2 class="hero-title">{{ plan.route_name || plan.name }}</h2>
      <div class="hero-chips">
        <span v-if="plan.project" class="hc"><Icon name="badge" :size="13" /> {{ plan.project }}</span>
        <span v-if="plan.shift" class="hc"><Icon name="clock" :size="13" /> {{ t("shift." + plan.shift) }}</span>
        <span v-if="plan.driver" class="hc"><Icon name="user" :size="13" /> {{ plan.driver }}</span>
        <span v-if="plan.vehicle" class="hc"><Icon name="truck" :size="13" /> {{ plan.vehicle }}</span>
        <span class="hc"><Icon name="pin" :size="13" /> {{ t("list.stops", { n: plan.total_stops }) }}</span>
      </div>
    </div>
    <Badge :theme="badgeTheme" size="lg" :label="t('approval.' + plan.approval)" />
  </div>

  <TabButtons
    class="tabs"
    :buttons="tabButtons"
    :model-value="tab"
    @update:model-value="openTab"
  />

  <div class="panel-area">
    <!-- Rendered on demand. Keeping every panel mounted and merely hidden fired the boarding
         and route reads the moment any plan was opened, which cost two requests per card on
         the queue-clearing path for panels nobody looked at. -->
    <ApprovalPanel v-if="tab === 'approval'" :plan="plan" />
    <BoardingPanel v-else-if="tab === 'boarding'" :trip-name="tripName" :active="true" />
    <RoutePanel v-else-if="tab === 'route'" :plan-name="plan.name" />
    <DriverMap v-else-if="tab === 'map'" :trip-name="tripName" :active="true" />
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { Badge, TabButtons } from "frappe-ui";

import { useMediaQuery } from "@shared/useBreakpoint.js";

import Icon from "../Icon.vue";
import ApprovalPanel from "./ApprovalPanel.vue";
import BoardingPanel from "./BoardingPanel.vue";
import DriverMap from "./DriverMap.vue";
import RoutePanel from "./RoutePanel.vue";
import { tabsFor } from "../tabs.js";
import { useI18n } from "@/i18n";

const props = defineProps({
  plan: { type: Object, required: true },
  tab: { type: String, required: true },
  wide: { type: Boolean, default: false },
});

const { t } = useI18n();
const router = useRouter();
const narrow = useMediaQuery("(max-width: 640px)");

const tripName = computed(() => props.plan.trip?.name || null);
const badgeTheme = computed(
  () => ({ Pending: "orange", Approved: "green", Rejected: "red" })[props.plan.approval] || "gray",
);

const tabButtons = computed(() =>
  tabsFor(props.wide).map((key) => ({ label: t("tabs." + key), value: key })),
);

/* The tab control asks for a screen; the address grants it. Writing a local ref here would put
   a second writer beside the URL, and assigning that ref its current value fires no watcher —
   which is exactly why re-opening the tab already on screen used to do nothing. */
function openTab(key) {
  if (!key || key === props.tab) return;
  router.push({ name: "plan", params: { name: props.plan.name, tab: key } });
}
</script>
