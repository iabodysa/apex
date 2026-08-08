<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="emp-narrow">
    <section class="emp-card">
      <header class="emp-card-head">
        <span class="emp-ic"><Icon name="fuel" :size="17" /></span>
        <div class="emp-card-titles">
          <h2>{{ t("emp.fuel.formTitle") }}</h2>
          <p class="emp-hint">{{ t("emp.fuel.hint") }}</p>
        </div>
      </header>

      <div v-if="stations.state.status === 'loading'" class="emp-skel" aria-hidden="true" />

      <LoadError
        v-else-if="stations.state.status === 'error'"
        :title="t('emp.loadError')"
        :detail="stations.state.error"
        :hint="t('emp.loadErrorHint')"
        :retry-label="t('common.retry')"
        @retry="stations.reload()"
      />

      <form v-else class="emp-form" @submit.prevent="onSubmit">
        <!-- The form stays on screen for an employee who holds no vehicle, with the reason
             beside it and the send button disabled: hiding it would leave him guessing why
             the screen he was pointed at is empty, and the server refuses the write anyway. -->
        <Alert
          v-if="blocked"
          theme="yellow"
          :title="t('emp.vehicle.empty')"
          :description="t('emp.fuel.needVehicleHint')"
          :dismissable="false"
        />

        <FormControl
          v-model="form.fuelGrade"
          type="select"
          size="md"
          :label="t('emp.fuel.fuelType')"
          :options="gradeOptions"
        />

        <FormControl
          id="ff-litres"
          v-model.number="form.litres"
          type="number"
          size="md"
          min="1"
          step="1"
          inputmode="numeric"
          :label="t('emp.fuel.quantity')"
          :description="t('emp.fuel.litresUnit')"
        />

        <FormControl
          v-model="form.station"
          type="select"
          size="md"
          :label="t('emp.fuel.station')"
          :options="stationOptions"
          :disabled="!stationOptions.length"
        />

        <FormControl
          v-model="form.notes"
          type="textarea"
          size="md"
          :rows="2"
          :label="t('emp.fuel.notes')"
          :placeholder="t('emp.fuel.notesPlaceholder')"
        />

        <ErrorMessage :message="formError" />

        <Button
          class="emp-block-btn"
          type="submit"
          variant="solid"
          theme="green"
          size="xl"
          :disabled="blocked"
          :loading="submitting"
          :loading-text="t('emp.fuel.sending')"
          :label="t('emp.fuel.submit')"
        />
      </form>
    </section>

    <section class="emp-card">
      <header class="emp-card-head">
        <span class="emp-ic"><Icon name="clipboard-list" :size="17" /></span>
        <div class="emp-card-titles">
          <h2>{{ t("emp.fuel.history") }}</h2>
          <p class="emp-hint">{{ t("emp.fuel.historyHint") }}</p>
        </div>
      </header>

      <div v-if="fuelRequests.state.status === 'loading'" class="emp-skel" aria-hidden="true" />

      <LoadError
        v-else-if="fuelRequests.state.status === 'error'"
        :title="t('emp.loadError')"
        :detail="fuelRequests.state.error"
        :hint="t('emp.loadErrorHint')"
        :retry-label="t('common.retry')"
        @retry="fuelRequests.reload()"
      />

      <EmptyState
        v-else-if="!fuelRequests.state.data.length"
        :title="t('emp.fuel.historyEmpty')"
        :hint="t('emp.fuel.historyEmptyHint')"
      >
        <template #icon><Icon name="clipboard-list" :size="20" /></template>
      </EmptyState>

      <ul v-else class="emp-trips">
        <li v-for="row in fuelRequests.state.data" :key="row.name" class="emp-trip">
          <Badge :theme="fuelMeta(row.statusKey).theme" size="md" :label="t(fuelMeta(row.statusKey).key)" />
          <div class="emp-route">
            <b><bdi>{{ row.litres }}</bdi> {{ t("emp.fuel.litresUnit") }}</b>
            <span>
              <bdi v-if="row.date">{{ row.date }}</bdi>
              <template v-if="row.station"> · {{ row.station }}</template>
              <template v-if="row.vehicle"> · <bdi>{{ row.vehicle }}</bdi></template>
            </span>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { Alert, Badge, Button, ErrorMessage, FormControl } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";

import Icon from "../Icon.vue";
import { fuelMeta } from "../statusMeta.js";
import { useAppToast } from "../toast.js";
import { ensureStations, submitFuel, useEmployee } from "../useEmployee.js";
import { useI18n } from "@/i18n";

const { t, resourceErrorMessage } = useI18n();
const { showToast } = useAppToast();
const { vehicle, stations, fuelRequests, grades, form, submitting, hasVehicle } = useEmployee();

const formError = ref("");

/* Only once the vehicle read has answered — a form disabled while it is still loading would
   flicker between states on a slow connection. */
const blocked = computed(() => vehicle.state.status === "ready" && !hasVehicle.value);

const gradeOptions = computed(() =>
  grades.map((g) => ({ label: t("fuelGrade." + g), value: g })),
);
const stationOptions = computed(() =>
  stations.state.data.map((s) => ({ label: s, value: s })),
);

onMounted(ensureStations);

async function onSubmit() {
  formError.value = "";
  const res = await submitFuel();
  if (res.ok) {
    showToast(t("emp.fuel.sent"), "green");
    return;
  }
  if (!res.error) return;
  /* The server's own words when it has them — the quota gate and the binding check both raise
     a sentence the employee can act on — and the portal's fallback when it does not. */
  const msg = res.error.messages?.[0] || resourceErrorMessage(res.error, "emp.fuel.error");
  formError.value = msg;
  showToast(msg, "red");
}
</script>
