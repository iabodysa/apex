<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <EmptyState :title="title" :hint="hint">
    <template #icon><Icon :name="isScopeEmpty ? 'lock' : icon" :size="20" /></template>
    <template v-if="!isScopeEmpty && anyFilterActive" #action>
      <div class="fp-empty-actions">
        <p v-if="activeFilterChips.length" class="fp-empty-filters">
          {{ t("main.activeFilters") }}
          <span v-for="(chip, i) in activeFilterChips" :key="i" class="fp-chip">{{ chip }}</span>
        </p>
        <Button variant="solid" theme="green" size="xl" :label="t('main.clearFilters')" @click="resetFilters()" />
      </div>
    </template>
  </EmptyState>
</template>

<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";

import Icon from "../Icon.vue";
import { useBoardContext } from "../boardContext.js";

/* Three different nothings, and the board must never confuse them: no project is an access
   gap the supervisor has to raise with his manager, no match is his own filters, and an empty
   fleet is the truth. */
defineProps({
  icon: { type: String, default: "car" },
});

const { t, state, board, filters } = useBoardContext();
const { isScopeEmpty } = board;
const { anyFilterActive, resetFilters } = state;
const { activeFilterChips } = filters;

const title = computed(() => {
  if (isScopeEmpty.value) return t("main.noScope");
  if (anyFilterActive.value) return t("main.noResultsFilters");
  return t("main.noVehicles");
});
const hint = computed(() => (isScopeEmpty.value ? t("main.noScopeHint") : ""));
</script>
