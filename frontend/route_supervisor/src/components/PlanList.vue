<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <ul class="plan-ledger">
    <li v-for="plan in resolvedItems" :key="plan.name">
      <router-link
        class="plan-row"
        :class="{ 'is-selected': plan.name === selectedName }"
        :to="{ name: 'plan', params: { name: plan.name, tab: targetTab(plan) } }"
        :aria-current="plan.name === selectedName ? 'page' : undefined"
      >
        <span class="plan-row-seam" aria-hidden="true" />
        <span class="plan-row-main">
          <span class="plan-row-title"><bdi dir="auto">{{ plan.route_name || plan.name }}</bdi></span>
          <span class="plan-row-meta">
            <span v-if="plan.project"><Icon name="badge" :size="13" /> <bdi dir="auto">{{ plan.project }}</bdi></span>
            <span v-if="plan.shift"><Icon name="clock" :size="13" /> {{ t("shift." + plan.shift) }}</span>
            <span><Icon name="pin" :size="13" /> <bdi dir="auto">{{ t("list.stops", { n: plan.total_stops }) }}</bdi></span>
          </span>
          <span class="plan-row-assignment">
            <span v-if="plan.driver"><Icon name="user" :size="13" /> <bdi dir="auto">{{ plan.driver }}</bdi></span>
            <span v-if="plan.vehicle"><Icon name="truck" :size="13" /> <bdi>{{ plan.vehicle }}</bdi></span>
          </span>
        </span>

        <span class="plan-row-state">
          <Badge
            :label="statusLabel(plan)"
            :theme="statusTheme(plan)"
            variant="subtle"
            size="lg"
          />
          <span v-if="plan.trip?.boarding" class="plan-row-progress">
            <Progress
              :value="pct(plan.trip.boarding.boarded, plan.trip.boarding.expected)"
              size="sm"
            />
            <bdi>{{ plan.trip.boarding.boarded }}/{{ plan.trip.boarding.expected || 0 }}</bdi>
          </span>
        </span>
      </router-link>
    </li>
  </ul>
</template>

<script setup>
import { computed } from "vue";
import { Badge, Progress } from "frappe-ui";

import Icon from "../Icon.vue";
import { pct } from "../fmt.js";
import { usePlans } from "../usePlans.js";
import { useI18n } from "@/i18n";

const props = defineProps({
  items: { type: Array, default: null },
  selectedName: { type: String, default: "" },
  mode: { type: String, default: "all" },
});

const { t } = useI18n();
const { plans } = usePlans();
const resolvedItems = computed(() => props.items || plans.value);

function targetTab(plan) {
  if (plan.approval === "Pending" || plan.approval === "Rejected") return "approval";
  if (props.mode === "history") return "route";
  return plan.trip ? "boarding" : "route";
}

function statusLabel(plan) {
  if (plan.approval === "Rejected") return t("approval.Rejected");
  if (plan.approval === "Pending") return t("approval.Pending");
  const status = plan.trip?.status;
  return status ? t("tripStatus." + status) : t("approval.Approved");
}

function statusTheme(plan) {
  if (plan.approval === "Rejected" || plan.trip?.status === "Cancelled") return "red";
  if (plan.approval === "Pending" || plan.trip?.status === "Dispatched") return "orange";
  if (plan.trip?.status === "Completed") return "green";
  return "blue";
}
</script>
