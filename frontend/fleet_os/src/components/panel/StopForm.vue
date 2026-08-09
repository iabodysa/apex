<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="subform subform-red">
    <h4 class="psect-title"><Icon name="circle-pause" :size="14" /> {{ t("stopForm.title") }}</h4>

    <div class="form-grid">
      <FormControl v-model="sf.reason" type="select" size="md" :label="t('stopForm.stopReason')" :options="reasonOptions" />
      <FormControl v-model="sf.nextStatus" type="select" size="md" :label="t('stopForm.nextStatus')" :options="nextOptions" />
    </div>

    <FormControl v-model="sf.notes" type="textarea" size="md" :rows="2" :label="t('stopForm.notes')" :placeholder="t('stopForm.notesPlaceholder')" />

    <div class="form-actions">
      <Button variant="outline" size="xl" :label="t('common.cancel')" @click="close()" />
      <Button variant="solid" theme="red" size="xl" :label="t('stopForm.confirm')" @click="actions.confirmStop()">
        <template #prefix><Icon name="circle-pause" :size="15" /></template>
      </Button>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { Button, FormControl } from "frappe-ui";

import Icon from "../../Icon.vue";
import { useBoardContext } from "../../boardContext.js";

const { t, actions, subForm } = useBoardContext();
const { sf } = actions;

/* The reason travels to the server as free text, so the option value IS the translated
   sentence — the record keeps what the supervisor actually read and chose. */
const reasonOptions = computed(() =>
  [
    "",
    "reasonContractEnd",
    "reasonTransfer",
    "reasonProjectStopped",
    "reasonVehicleFault",
    "reasonDriverRequest",
    "reasonViolation",
    "reasonOther",
  ].map((key) =>
    key
      ? { label: t("stopForm." + key), value: t("stopForm." + key) }
      : { label: t("stopForm.chooseReason"), value: "" },
  ),
);

const nextOptions = computed(() => [
  { label: t("stopForm.nextAvailable"), value: "available" },
  { label: t("stopForm.nextWorkshop"), value: "workshop" },
  { label: t("stopForm.nextStopped"), value: "stopped" },
]);

const close = () => {
  subForm.value = null;
};
</script>
