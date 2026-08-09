<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <ListSkeleton v-if="gridRes.loading && !grid" :rows="6" :label="t('beds.loadingLabel')" />

  <LoadError
    v-else-if="gridRes.error"
    :title="t('errors.gridFailed')"
    :detail="gridErrorMessage"
    :hint="t('errors.retryHint')"
    :retry-label="t('common.retry')"
    @retry="gridRes.reload()"
  />

  <EmptyState v-else-if="!hasBeds" :title="t('beds.empty')">
    <template #icon><Icon name="bed" :size="24" /></template>
  </EmptyState>

  <template v-else>
    <div class="section-head">
      <h2>{{ t("transfer.title") }}</h2>
      <Button variant="ghost" size="md" :label="t('common.refresh')" @click="gridRes.reload()">
        <template #icon><Icon name="refresh" :size="18" /></template>
      </Button>
    </div>

    <p class="status-note" :class="selection ? 'status-ok' : 'status-warn'">
      {{ selection ? t("transfer.selected", { name: selection.name }) : t("transfer.pickSource") }}
    </p>
    <p v-if="selection" class="hint">{{ t("transfer.pickTarget") }}</p>
    <p v-if="!canTransfer" class="hint">{{ t("access.needTransfer") }}</p>

    <BedGrid
      :grid="grid"
      :selected-bed="selection ? selection.bed : ''"
      :occupied-only="!selection"
      :free-only="!!selection"
      @bed="onBed"
    />

    <div v-if="selection" class="hz-dock">
      <Button
        class="dock-btn"
        size="xl"
        variant="outline"
        :label="t('transfer.clear')"
        @click="setSelection(null)"
      />
    </div>

    <Dialog
      :modelValue="!!target"
      :options="{ title: moveTitle, size: 'sm' }"
      @update:modelValue="(open) => !open && (target = null)"
    >
      <template #body-content>
        <div class="stack">
          <FormControl
            type="textarea"
            size="lg"
            :label="t('transfer.reason')"
            :placeholder="t('transfer.reasonPlaceholder')"
            v-model="reason"
          />
          <ErrorMessage v-if="moveError" :message="moveError" />
        </div>
      </template>
      <template #actions>
        <div class="sheet-actions">
          <Button
            class="dock-btn"
            size="2xl"
            variant="solid"
            theme="green"
            :disabled="!canTransfer"
            :loading="!!busy"
            :loading-text="t('transfer.moving')"
            :label="moveTitle"
            @click="doTransfer"
          />
          <Button size="xl" variant="outline" :label="t('common.cancel')" @click="target = null" />
        </div>
      </template>
    </Dialog>
  </template>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Button, Dialog, ErrorMessage, FormControl, createResource, toast } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import BedGrid from "../components/BedGrid.vue";
import Icon from "../components/Icon.vue";
import ListSkeleton from "../components/ListSkeleton.vue";
import LoadError from "../components/LoadError.vue";
import { call } from "@shared/call";
import { useI18n, apiErrorMessage, resourceErrorMessage } from "../i18n";
import { can } from "../portal.js";
import { building, localDate } from "../session";

const { t } = useI18n();

const canTransfer = can("transfer");

const selection = ref(null);
const target = ref(null);
const reason = ref("");
const moveError = ref("");
const busy = ref("");

const gridRes = createResource({
  url: "apex.habitat.api.front_desk.get_building_grid",
  makeParams: () => ({ building: building.value }),
});

const grid = computed(() => gridRes.data || null);
const gridErrorMessage = computed(() => resourceErrorMessage(gridRes.error, "errors.gridFailed"));
const hasBeds = computed(() => !!(grid.value && grid.value.floors && grid.value.floors.length));

const moveTitle = computed(() =>
  selection.value ? t("transfer.cta", { name: selection.value.name }) : "",
);

function setSelection(next) {
  selection.value = next;
  target.value = null;
  reason.value = "";
  moveError.value = "";
}

function onBed(bed) {
  if (!selection.value) {
    if (bed.bed_color !== "red" || !bed.occupant) return;
    setSelection({ bed: bed.bed, name: bed.occupant.employee_name });
    return;
  }
  if (bed.bed_color !== "green") return;
  if (bed.bed === selection.value.bed) {
    moveError.value = t("transfer.targetSame");
    return;
  }
  moveError.value = "";
  target.value = bed;
}

async function doTransfer() {
  if (!selection.value || !target.value || busy.value) return;
  busy.value = target.value.bed;
  moveError.value = "";
  try {
    await call("apex.habitat.api.transfer_board.transfer_occupant", {
      args: {
        source_bed: selection.value.bed,
        target_bed: target.value.bed,
        transfer_date: localDate(),
        reason: reason.value || null,
      },
      type: "POST",
    });
    toast.create({ type: "success", message: t("transfer.moved") });
    setSelection(null);
    gridRes.reload();
  } catch (err) {
    moveError.value = apiErrorMessage(err);
  } finally {
    busy.value = "";
  }
}

watch(building, () => {
  setSelection(null);
  if (building.value) gridRes.fetch();
});

onMounted(() => {
  if (building.value) gridRes.fetch();
});
</script>

<style scoped>
.sheet-actions {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
</style>
