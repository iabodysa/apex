<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <DecisionStage>
    <router-link :to="backTo" class="back-link">
      <Icon name="chevron" :size="18" />
      <span>{{ backLabel }}</span>
    </router-link>

    <header class="plan-record-heading">
      <div>
        <p>{{ t("plan.eyebrow") }}</p>
        <h1><bdi dir="auto">{{ plan.route_name || plan.name }}</bdi></h1>
        <span><bdi dir="auto">{{ plan.project || t("plan.noProject") }}</bdi></span>
      </div>
      <Badge
        :label="t('approval.' + plan.approval)"
        :theme="statusTheme"
        variant="subtle"
        size="lg"
      />
    </header>

    <dl class="plan-facts">
      <div>
        <dt>{{ t("approval.driver") }}</dt>
        <dd><bdi dir="auto">{{ plan.driver || t("common.none") }}</bdi></dd>
      </div>
      <div>
        <dt>{{ t("approval.vehicle") }}</dt>
        <dd><bdi dir="auto">{{ plan.vehicle || t("common.none") }}</bdi></dd>
      </div>
      <div>
        <dt>{{ t("list.shift") }}</dt>
        <dd>{{ plan.shift ? t("shift." + plan.shift) : t("common.none") }}</dd>
      </div>
      <div>
        <dt>{{ t("approval.stops") }}</dt>
        <dd><bdi>{{ plan.total_stops }}</bdi></dd>
      </div>
    </dl>

    <TabButtons
      class="plan-tabs"
      :buttons="tabButtons"
      :model-value="tab"
      @update:model-value="openTab"
    />

    <section class="plan-panel" :aria-label="t('tabs.' + tab)">
      <ApprovalPanel v-if="tab === 'approval'" :plan="plan" />
      <BoardingPanel v-else-if="tab === 'boarding'" :trip-name="tripName" :active="true" />
      <RoutePanel v-else-if="tab === 'route'" :plan-name="plan.name" />
      <DriverMap v-else-if="tab === 'map'" :trip-name="tripName" :active="true" />
    </section>
  </DecisionStage>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { Badge, TabButtons } from "frappe-ui";

import DecisionStage from "@shared/components/DecisionStage.vue";

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
  backTo: { type: String, default: "/routes" },
});

const { t } = useI18n();
const router = useRouter();

const tripName = computed(() => props.plan.trip?.name || null);
const statusTheme = computed(
  () => ({ Pending: "orange", Approved: "green", Rejected: "red" })[props.plan.approval] || "gray",
);
const backLabel = computed(() => {
  if (props.backTo === "/approvals") return t("nav.inbox");
  if (props.backTo === "/history") return t("nav.history");
  return t("nav.routes");
});
const tabButtons = computed(() =>
  tabsFor(props.wide).map((key) => ({ label: t("tabs." + key), value: key })),
);

function openTab(key) {
  if (!key || key === props.tab) return;
  router.push({ name: "plan", params: { name: props.plan.name, tab: key } });
}
</script>
