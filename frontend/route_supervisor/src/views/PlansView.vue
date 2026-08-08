<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="work">
    <PlanList v-if="showList" :selected-name="selectedName" />

    <section v-if="showDetail" class="detail">
      <PlanDetail v-if="selectedPlan" :plan="selectedPlan" :tab="tab" :wide="wide" />

      <EmptyState
        v-else-if="selectedName && loadState === 'ready'"
        :title="t('list.gonePlan')"
        :hint="t('list.gonePlanHint')"
      >
        <template #icon><Icon name="triangle-alert" :size="20" :stroke-width="1.6" /></template>
        <template #action>
          <Button variant="outline" size="lg" :label="t('nav.plans')" @click="router.push('/')" />
        </template>
      </EmptyState>

      <EmptyState v-else-if="!selectedName" :title="t('list.pickPlan')" :hint="t('list.pickPlanHint')">
        <template #icon><Icon name="route" :size="20" :stroke-width="1.6" /></template>
      </EmptyState>
    </section>

    <aside v-if="wide && selectedPlan" class="live">
      <DriverMap :trip-name="selectedTrip" :active="true" />
    </aside>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import { useMediaQuery } from "@shared/useBreakpoint.js";

import Icon from "../Icon.vue";
import DriverMap from "../components/DriverMap.vue";
import PlanDetail from "../components/PlanDetail.vue";
import PlanList from "../components/PlanList.vue";
import { usePlans } from "../usePlans.js";
import { TAB_KEYS, tabsFor } from "../tabs.js";
import { useI18n } from "@/i18n";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { planByName, loadState } = usePlans();

const wide = useMediaQuery("(min-width: 1280px)");
const narrow = useMediaQuery("(max-width: 640px)");

const selectedName = computed(() => (route.name === "plan" ? String(route.params.name) : ""));
const selectedPlan = computed(() => (selectedName.value ? planByName(selectedName.value) : null));
const selectedTrip = computed(() => selectedPlan.value?.trip?.name || null);

/* The map is a pane at this width, never a tab, so a link that names it resolves to the first
   tab instead of lighting a tab over an empty panel. */
const tab = computed(() => {
  const asked = String(route.params.tab || "");
  return tabsFor(wide.value).includes(asked) ? asked : TAB_KEYS[0];
});

/* One pane at a time on a phone: the list until a plan is chosen, then the plan with a way
   back. Both states are addresses, so Back and a shared link both land where they should. */
const showList = computed(() => !narrow.value || !selectedName.value);
const showDetail = computed(() => !narrow.value || Boolean(selectedName.value));
</script>
