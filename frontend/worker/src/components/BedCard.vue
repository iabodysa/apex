<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <Panel :title="t('home.bed')">
    <template v-if="bed" #status>
      <Badge class="tone-badge" theme="green" variant="subtle" size="lg" :label="bedCode" />
    </template>

    <dl v-if="bed" class="bed-facts">
      <div v-if="building" class="bed-fact">
        <dt>{{ t("accommodation.building") }}</dt>
        <dd><bdi>{{ building }}</bdi></dd>
      </div>
      <div v-if="room" class="bed-fact">
        <dt>{{ t("accommodation.room") }}</dt>
        <dd><bdi>{{ room }}</bdi></dd>
      </div>
      <div v-if="bed.floor != null" class="bed-fact">
        <dt>{{ t("accommodation.floor") }}</dt>
        <dd><bdi>{{ bed.floor }}</bdi></dd>
      </div>
      <div v-if="bed.check_in_date" class="bed-fact">
        <dt>{{ t("accommodation.checkIn") }}</dt>
        <dd><bdi>{{ formatDate(bed.check_in_date) }}</bdi></dd>
      </div>
    </dl>

    <EmptyState v-else :title="t('accommodation.empty')" :hint="t('accommodation.emptyHint')">
      <template #icon><Icon name="bed" :size="22" /></template>
    </EmptyState>
  </Panel>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import Panel from "@shared/components/Panel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";
import { formatDate } from "../utils/datetime";

const { t } = useI18n();

const props = defineProps({
  bed: { type: Object, default: null },
});

const bedCode = computed(() => props.bed?.bed_code || props.bed?.name || "");
const building = computed(() => props.bed?.building_name || props.bed?.building || "");
const room = computed(() => props.bed?.room_number || props.bed?.room || "");
</script>

<style scoped>
.bed-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3) var(--sp-5);
}
.bed-fact {
  min-width: 0;
}
.bed-fact dt {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
  letter-spacing: 0.02em;
}
.bed-fact dd {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  line-height: 1.4;
}
</style>
