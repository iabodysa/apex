<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <EmptyState v-if="!vehicle.history.length" :title="t('logTab.empty')" :hint="t('logTab.emptyHint')">
    <template #icon><Icon name="clipboard-list" :size="20" /></template>
  </EmptyState>

  <template v-else>
    <h3 class="psect-title">{{ t("logTab.fullTimeline", { n: vehicle.history.length }) }}</h3>
    <ol class="tl">
      <li v-for="(item, i) in items" :key="i" class="tl-item">
        <span class="tl-ic" :class="item.d.status === 'Active' ? 'ti-active' : 'ti-stopped'">
          <Icon name="user" :size="15" />
        </span>
        <div class="tl-info">
          <div class="tl-head">
            {{ item.d.name_ar || item.d.name_en || t("logTab.driver") }}
            <Badge
              :theme="item.d.status === 'Active' ? 'green' : 'gray'"
              size="sm"
              :label="item.d.status === 'Active' ? t('logTab.active') : t('logTab.ended')"
            />
          </div>
          <div class="tl-sub">
            {{ item.d.name_en || "" }}
            · <Icon name="phone" :size="11" /> <bdi>{{ item.d.mobile || t("common.none") }}</bdi>
            · <Icon name="id-card" :size="11" /> <bdi>{{ item.d.driver_id || t("common.none") }}</bdi>
          </div>
          <div class="tl-sub">
            <Icon name="package" :size="11" /> {{ fmt.trim(item.d.project) || t("common.none") }}
            · <Icon name="pin" :size="11" /> {{ item.d.area || t("common.none") }}
            · <Icon name="building" :size="11" /> {{ item.d.branch_receive || t("common.none") }}
          </div>
          <span class="tl-dates">
            <bdi>{{ item.d.date_receive || t("common.none") }}</bdi> →
            <bdi>{{ item.d.date_deliver || (item.d.status === "Active" ? t("common.ongoing") : t("common.none")) }}</bdi>
          </span>
          <span v-if="durationOf(item.d)" class="tl-dur">{{ durationOf(item.d) }}</span>
          <p v-if="item.d.reason" class="tl-reason">{{ t("logTab.reason", { v: item.d.reason }) }}</p>
          <p v-if="item.d.notes" class="tl-note">{{ t("logTab.note", { v: item.d.notes }) }}</p>
        </div>
      </li>
    </ol>
  </template>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";

import Icon from "../../Icon.vue";
import { useBoardContext } from "../../boardContext.js";

const props = defineProps({
  vehicle: { type: Object, required: true },
});

const { t, fmt } = useBoardContext();

const items = computed(() => fmt.historyItems(props.vehicle));

/* An open assignment is measured to today; a closed one to the day it ended. */
const durationOf = (d) =>
  fmt.calcDur(d.date_receive, d.date_deliver || (d.status === "Active" ? fmt.today() : ""));
</script>
