<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="subform subform-red">
    <h4 class="psect-title"><Icon name="shield-alert" :size="14" /> {{ t("stolenForm.title") }}</h4>

    <div class="form-grid">
      <FormControl v-model="stf.date" type="date" size="md" lang="en" :label="t('stolenForm.theftDate')" :required="true" />
      <FormControl v-model="stf.police" type="text" size="md" :label="t('stolenForm.policeNumber')" :placeholder="t('stolenForm.policePlaceholder')" />
      <FormControl v-model="stf.location" type="text" size="md" :label="t('stolenForm.location')" :placeholder="t('stolenForm.locationPlaceholder')" />
      <FormControl v-model="stf.reporter" type="text" size="md" :label="t('stolenForm.reportedBy')" :placeholder="t('stolenForm.reporterPlaceholder')" />
    </div>

    <FormControl v-model="stf.desc" type="textarea" size="md" :rows="2" :label="t('stolenForm.details')" :placeholder="t('stolenForm.detailsPlaceholder')" />
    <FormControl v-model="stf.notes" type="textarea" size="md" :rows="2" :label="t('stolenForm.extraNotes')" />

    <div class="form-actions">
      <Button variant="outline" size="xl" :label="t('common.cancel')" @click="close()" />
      <Button variant="solid" theme="red" size="xl" :label="t('stolenForm.confirm')" @click="actions.submitStolen()">
        <template #prefix><Icon name="shield-alert" :size="15" /></template>
      </Button>
    </div>
  </div>
</template>

<script setup>
import { Button, FormControl } from "frappe-ui";

import Icon from "../../Icon.vue";
import { useBoardContext } from "../../boardContext.js";

const { t, actions, subForm } = useBoardContext();
const { stf } = actions;

const close = () => {
  subForm.value = null;
};
</script>
