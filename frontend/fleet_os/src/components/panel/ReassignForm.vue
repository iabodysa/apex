<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="subform subform-green">
    <h4 class="psect-title"><Icon name="rotate-cw" :size="14" /> {{ t("reassignForm.title") }}</h4>

    <Alert
      v-if="currentDriverName"
      class="subform-note"
      theme="yellow"
      :title="t('reassignForm.autoLockHint', { name: currentDriverName })"
      :dismissable="false"
    />

    <div class="form-grid">
      <div class="ff">
        <FormLabel :label="t('reassignForm.driver')" :required="true" />
        <!-- The picker binds the driver's record name; the typed text is only a search term,
             and the server checks the id again before it writes. -->
        <Autocomplete
          :options="driverOptions"
          :model-value="selectedOption"
          :loading="driverLoading"
          :placeholder="t('reassignForm.driverPlaceholder')"
          @update:query="onDriverQuery"
          @update:model-value="pickDriver"
        />
        <Button class="dp-newlink" variant="ghost" size="lg" :label="t('reassignForm.newDriver')" @click="openNewDriverForm()">
          <template #prefix><Icon name="user" :size="13" /></template>
        </Button>
      </div>

      <FormControl
        v-model="rf.date"
        type="date"
        size="md"
        lang="en"
        :label="t('reassignForm.receiveDate')"
      />
    </div>

    <Checkbox v-model="rf.captureHandover" :label="t('reassignForm.captureHandover')" />

    <div v-if="rf.captureHandover" class="ho-box">
      <div class="form-grid">
        <FormControl v-model.number="rf.odometer" type="number" size="md" min="0" :label="t('reassignForm.odometer')" />
        <FormControl
          v-model="rf.checklistTemplate"
          type="text"
          size="md"
          :label="t('reassignForm.checklistTemplate')"
          :placeholder="t('reassignForm.checklistPlaceholder')"
        />
      </div>
      <FormControl v-model="rf.conditionNotes" type="textarea" size="md" :rows="2" :label="t('reassignForm.conditionNotes')" />
      <p class="ho-hint"><Icon name="clipboard-list" :size="13" /> {{ t("reassignForm.handoverHint") }}</p>
    </div>

    <!-- The reassign stands even when the handover draft fails, so the fact that it is missing
         stays on screen rather than leaving with a toast. -->
    <Alert
      v-if="handoverMissing"
      class="subform-note"
      theme="yellow"
      :title="t('reassignForm.handoverMissing')"
      :description="t('reassignForm.handoverMissingHint')"
      :dismissable="false"
    />

    <div class="form-actions">
      <Button variant="outline" size="xl" :label="t('common.cancel')" @click="close()" />
      <Button
        variant="solid"
        theme="green"
        size="xl"
        :disabled="!rf.driverName"
        :label="t('reassignForm.assignAndLock')"
        @click="submitReassign()"
      >
        <template #prefix><Icon name="lock" :size="15" /></template>
      </Button>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { Alert, Autocomplete, Button, Checkbox, FormControl, FormLabel } from "frappe-ui";

import Icon from "../../Icon.vue";
import { useBoardContext } from "../../boardContext.js";

const props = defineProps({
  vehicle: { type: Object, required: true },
});

const { t, assignment, subForm } = useBoardContext();
const {
  rf,
  driverOptions,
  driverLoading,
  handoverMissing,
  onDriverQuery,
  pickDriver,
  openNewDriverForm,
  submitReassign,
} = assignment;

const currentDriverName = computed(() => {
  const d = props.vehicle.current_driver;
  return d ? d.name_ar || d.name_en || "" : "";
});

const selectedOption = computed(() =>
  rf.driverName ? { label: rf.driverLabel, value: rf.driverName } : null,
);

const close = () => {
  subForm.value = null;
};
</script>
