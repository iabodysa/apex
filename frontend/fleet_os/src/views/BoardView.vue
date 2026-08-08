<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <StatusPills />

  <Alert
    v-if="readerErrors.length"
    class="fp-banner"
    theme="yellow"
    :title="t('main.partialBoard')"
    :description="t('main.partialBoardDetail', { sections: readerErrors.join('، ') })"
    :dismissable="false"
  />

  <div class="layout">
    <FleetSidebar />

    <div class="main">
      <FleetToolbar />

      <div v-if="selectMode && selectedCount" class="fp-bulk-bar">
        <span class="fp-bulk-count">{{ t("bulk.selected", { n: selectedCount }) }}</span>
        <FormControl
          v-model="bulkNote"
          class="fp-bulk-note"
          type="text"
          size="md"
          :placeholder="t('stopForm.notesPlaceholder')"
          :label="t('stopForm.notes')"
        />
        <div class="fp-bulk-actions">
          <Button variant="solid" theme="red" size="xl" :label="t('bulk.stopSelected')" @click="actions.bulkStop()">
            <template #prefix><Icon name="circle-pause" :size="14" /></template>
          </Button>
          <Button variant="outline" size="xl" :label="t('bulk.workshopSelected')" @click="actions.bulkWorkshop()">
            <template #prefix><Icon name="wrench" :size="14" /></template>
          </Button>
          <Button variant="ghost" size="xl" :label="t('bulk.clear')" @click="clearSelection()">
            <template #prefix><Icon name="x" :size="14" /></template>
          </Button>
        </div>
      </div>

      <Alert
        v-if="loadState === 'ready' && reloadStale"
        class="fp-banner"
        theme="yellow"
        :title="t('main.staleData')"
        :dismissable="false"
      />

      <div v-if="loadState === 'error'" class="fp-pad">
        <LoadError
          :title="t('main.loadFailed')"
          :detail="loadError || ''"
          :hint="t('main.loadFailedHint')"
          :retry-label="t('common.retry')"
          @retry="board.loadFleet()"
        />
      </div>

      <div v-else-if="loadState === 'loading'" class="cards-wrap">
        <div class="cards-grid" aria-hidden="true">
          <div v-for="n in 8" :key="n" class="fp-skel-card">
            <div class="fp-skel-line" style="width: 40%"></div>
            <div class="fp-skel-line" style="width: 70%"></div>
            <div class="fp-skel-line" style="width: 55%"></div>
            <div class="fp-skel-line" style="width: 80%"></div>
          </div>
        </div>
      </div>

      <FleetCardGrid v-else-if="view === 'cards'" />
      <FleetDriverLens v-else-if="view === 'drivers'" />
      <FleetTable v-else />
    </div>
  </div>
</template>

<script setup>
import { Alert, Button, FormControl } from "frappe-ui";

import LoadError from "@shared/components/LoadError.vue";

import Icon from "../Icon.vue";
import FleetCardGrid from "../components/FleetCardGrid.vue";
import FleetDriverLens from "../components/FleetDriverLens.vue";
import FleetSidebar from "../components/FleetSidebar.vue";
import FleetTable from "../components/FleetTable.vue";
import FleetToolbar from "../components/FleetToolbar.vue";
import StatusPills from "../components/StatusPills.vue";
import { useBoardContext } from "../boardContext.js";

const { t, state, board, selection, actions } = useBoardContext();

/* Destructured to top-level bindings on purpose: `<script setup>` unwraps a ref that is a
   top-level binding inside the template, but not one reached through a plain object. */
const { loadState, loadError, reloadStale, readerErrors } = board;
const { view } = state;
const { selectMode, selectedCount, clearSelection } = selection;
const { bulkNote } = actions;
</script>
