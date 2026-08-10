<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <h3 class="psect-title">
    <Icon :name="isDamages ? 'hammer' : 'crash'" :size="14" />
    {{ isDamages ? t("damages.title") : t("accidents.title") }}
  </h3>

  <EmptyState
    v-if="!rows.length"
    :title="isDamages ? t('damages.empty') : t('accidents.empty')"
  >
    <template #icon><Icon :name="isDamages ? 'hammer' : 'crash'" :size="20" /></template>
  </EmptyState>

  <article v-for="(row, i) in rows" v-else :key="i" class="incident-card">
    <header class="incident-card-head">
      <Badge :theme="settled(row) ? 'green' : isDamages ? 'red' : 'orange'" size="sm" :label="badgeLabel(row)" />
      <bdi class="incident-date">{{ row.date || t("common.none") }}</bdi>
      <span v-if="row.cost" class="incident-cost">
        <Icon name="banknote" :size="12" />
        <bdi class="price-lockup" dir="ltr">&#xFDFC;{{ row.cost }}</bdi>
      </span>
    </header>
    <div class="incident-card-body">
      <span class="inc-label">{{ isDamages ? t("damages.description") : t("accidents.description") }}</span>
      <p>{{ row.description || t("common.none") }}</p>
    </div>
  </article>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";

import Icon from "../../Icon.vue";
import { useBoardContext } from "../../boardContext.js";

const props = defineProps({
  vehicle: { type: Object, required: true },
  kind: { type: String, required: true },
});

const { t } = useBoardContext();

const isDamages = computed(() => props.kind === "damages");
const rows = computed(() =>
  isDamages.value ? props.vehicle.damages : props.vehicle.accidents,
);

const settled = (row) => (isDamages.value ? row.status === "completed" : row.status === "closed");
const badgeLabel = (row) => {
  if (isDamages.value) return settled(row) ? t("damages.repaired") : t("damages.damage");
  return settled(row) ? t("accidents.closed") : t("accidents.accident");
};
</script>
