<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <StatusPills />

  <section v-if="readerErrors.length || reloadStale" class="board-notices" aria-live="polite">
    <Alert
      v-if="readerErrors.length"
      theme="yellow"
      :title="t('main.partialBoard')"
      :description="t('main.partialBoardDetail', { sections: readerErrors.join('، ') })"
      :dismissable="false"
    />
    <Alert
      v-if="reloadStale"
      theme="yellow"
      :title="t('main.staleData')"
      :dismissable="false"
    />
  </section>

  <div class="signal-workbench" :class="{ 'has-context': Boolean(openPlate) }">
    <FleetSidebar />

    <section class="working-set" :aria-label="t('main.workingSet')">
      <FleetToolbar />

      <Alert
        v-if="selectionLimitReached"
        class="selection-limit"
        theme="yellow"
        :title="t('bulk.limitReached', { n: maxSelection })"
        :dismissable="false"
      />

      <AsyncBoundary
        :state="loadState"
        :title="loadState === 'error' ? t('main.loadFailed') : ''"
        :message="loadState === 'error' ? loadError || t('main.loadFailedHint') : ''"
        :retry-label="loadState === 'error' ? t('common.retry') : ''"
        @retry="board.loadFleet()"
      >
        <FleetCardGrid v-if="view === 'cards'" />
        <FleetDriverLens v-else-if="view === 'drivers'" />
        <FleetTable v-else />
      </AsyncBoundary>

      <section v-if="bulkResult" class="bulk-outcome" aria-live="polite">
        <header>
          <h2>{{ t("bulk.outcomeTitle") }}</h2>
          <p>{{ t("bulk.summary", { ok: bulkResult.succeeded, failed: bulkResult.failed }) }}</p>
        </header>
        <ul>
          <li v-for="row in bulkResult.rows" :key="row.plate" :data-ok="row.ok">
            <StatusLabel
              :tone="row.ok ? 'success' : 'danger'"
              :label="row.ok ? t('bulk.succeeded') : t('bulk.failed')"
            />
            <bdi class="mono">{{ row.plate }}</bdi>
            <span v-if="row.error">{{ row.error }}</span>
          </li>
        </ul>
      </section>

      <ActionDock v-if="selectMode && selectedCount">
        <template #secondary>
          <FormControl
            v-model="bulkNote"
            class="bulk-note"
            type="text"
            size="md"
            :placeholder="t('stopForm.notesPlaceholder')"
            :label="t('stopForm.notes')"
          />
          <Button variant="ghost" size="xl" :label="t('bulk.clear')" @click="clearSelection()">
            <template #prefix><Icon name="x" :size="14" /></template>
          </Button>
        </template>
        <template #danger>
          <span class="bulk-count"><bdi>{{ selectedCount }}</bdi> {{ t("bulk.selectedShort") }}</span>
          <Button variant="outline" theme="red" size="xl" :label="t('bulk.stopSelected')" @click="actions.bulkStop()">
            <template #prefix><Icon name="circle-pause" :size="14" /></template>
          </Button>
          <Button variant="solid" theme="green" size="xl" :label="t('bulk.workshopSelected')" @click="actions.bulkWorkshop()">
            <template #prefix><Icon name="wrench" :size="14" /></template>
          </Button>
        </template>
      </ActionDock>
    </section>

    <VehiclePanel />
  </div>
</template>

<script setup>
import { Alert, Button, FormControl } from "frappe-ui";

import ActionDock from "@shared/components/ActionDock.vue";
import AsyncBoundary from "@shared/components/AsyncBoundary.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";

import Icon from "../Icon.vue";
import FleetCardGrid from "../components/FleetCardGrid.vue";
import FleetDriverLens from "../components/FleetDriverLens.vue";
import FleetSidebar from "../components/FleetSidebar.vue";
import FleetTable from "../components/FleetTable.vue";
import FleetToolbar from "../components/FleetToolbar.vue";
import StatusPills from "../components/StatusPills.vue";
import VehiclePanel from "../components/VehiclePanel.vue";
import { useBoardContext } from "../boardContext.js";

const { t, state, board, selection, actions } = useBoardContext();

const { loadState, loadError, reloadStale, readerErrors } = board;
const { view, openPlate } = state;
const {
  selectMode,
  selectedCount,
  clearSelection,
  selectionLimitReached,
  maxSelection,
} = selection;
const { bulkNote, bulkResult } = actions;
</script>
