<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="emp-narrow emp-fuel-scene">
    <section class="emp-sheet emp-fuel-request" aria-labelledby="emp-fuel-form-title">
      <header class="emp-ledger-head">
        <div>
          <span class="emp-ledger-kicker">{{ t("emp.fuel.requestKicker") }}</span>
          <h2 id="emp-fuel-form-title">{{ t("emp.fuel.formTitle") }}</h2>
        </div>
        <Icon name="fuel" :size="27" />
      </header>

      <div class="emp-binding" :data-state="vehicle.state.status">
        <div>
          <span>{{ t("emp.fuel.boundVehicle") }}</span>
          <template v-if="vehicle.state.status === 'ready' && vehicle.state.data">
            <strong><bdi>{{ vehicle.state.data.plate || vehicle.state.data.name }}</bdi></strong>
            <small><bdi>{{ vehicle.state.data.model || t("common.none") }}</bdi></small>
          </template>
          <strong v-else-if="vehicle.state.status === 'loading' || vehicle.state.status === 'idle'">
            {{ t("emp.fuel.checkingVehicle") }}
          </strong>
          <strong v-else-if="vehicle.state.status === 'error'">{{ t("emp.loadError") }}</strong>
          <strong v-else>{{ t("emp.vehicle.empty") }}</strong>
        </div>
        <Button
          v-if="vehicle.state.status === 'error'"
          variant="outline"
          size="xl"
          :label="t('common.retry')"
          @click="vehicle.reload()"
        />
      </div>

      <p class="emp-quota-note">{{ t("emp.fuel.quotaNote") }}</p>

      <AsyncBoundary
        :state="stationsState"
        :title="t('emp.loadError')"
        :message="stations.state.error"
        :retry-label="t('common.retry')"
        @retry="stations.reload()"
      >
        <form class="emp-form" @submit.prevent="onSubmit">
          <Alert
            v-if="vehicleMissing"
            theme="yellow"
            :title="t('emp.vehicle.empty')"
            :description="t('emp.fuel.needVehicleHint')"
            :dismissable="false"
          />

          <div class="emp-form-row">
            <FormControl
              v-model="form.fuelGrade"
              type="select"
              size="md"
              :label="t('emp.fuel.fuelType')"
              :options="gradeOptions"
            />

            <FormControl
              v-model.number="form.litres"
              type="number"
              size="md"
              min="1"
              step="1"
              inputmode="numeric"
              :label="t('emp.fuel.quantity')"
              :description="t('emp.fuel.litresUnit')"
            />
          </div>

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
            class="emp-primary-action"
            type="submit"
            variant="solid"
            theme="green"
            size="xl"
            :disabled="!canSubmit"
            :loading="submitting"
            :loading-text="t('emp.fuel.sending')"
            :label="t('emp.fuel.submit')"
          >
            <template #prefix><Icon name="send" :size="18" /></template>
          </Button>
        </form>
      </AsyncBoundary>
    </section>

    <section class="emp-sheet emp-fuel-history" aria-labelledby="emp-fuel-history-title">
      <header class="emp-ledger-head">
        <div>
          <span class="emp-ledger-kicker">{{ t("emp.fuel.historyKicker") }}</span>
          <h2 id="emp-fuel-history-title">{{ t("emp.fuel.history") }}</h2>
        </div>
        <strong class="emp-ledger-count tnum">
          <bdi>{{ formatInt(fuelRequests.state.data.length, lang) }}</bdi>
          <span>{{ t("emp.fuel.requestCountLabel") }}</span>
        </strong>
      </header>

      <AsyncBoundary
        :state="fuelHistoryState"
        :title="fuelHistoryState === 'empty' ? t('emp.fuel.historyEmpty') : t('emp.loadError')"
        :message="fuelHistoryState === 'empty' ? t('emp.fuel.historyEmptyHint') : fuelRequests.state.error"
        :retry-label="t('common.retry')"
        @retry="fuelRequests.reload()"
      >
        <ol class="emp-fuel-rows">
          <li v-for="(row, index) in fuelRequests.state.data" :key="row.name" class="emp-fuel-row">
            <span class="emp-trip-sequence tnum" aria-hidden="true">
              <bdi>{{ String(index + 1).padStart(2, "0") }}</bdi>
            </span>
            <div class="emp-route">
              <strong><bdi>{{ row.litres }}</bdi> {{ t("emp.fuel.litresUnit") }}</strong>
              <span>
                <bdi v-if="row.date">{{ formatDate(row.date, lang) }}</bdi>
                <template v-if="row.station"> · <bdi>{{ row.station }}</bdi></template>
                <template v-if="row.vehicle"> · <bdi>{{ row.vehicle }}</bdi></template>
              </span>
            </div>
            <Badge
              class="emp-trip-status"
              :theme="fuelMeta(row.statusKey).theme"
              size="md"
              :label="t(fuelMeta(row.statusKey).key)"
            />
          </li>
        </ol>
      </AsyncBoundary>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { Alert, Badge, Button, ErrorMessage, FormControl } from "frappe-ui";

import AsyncBoundary from "@shared/components/AsyncBoundary.vue";

import Icon from "../Icon.vue";
import { formatDate, formatInt } from "../fmt.js";
import { fuelMeta } from "../statusMeta.js";
import { useAppToast } from "../toast.js";
import { ensureStations, submitFuel, useEmployee } from "../useEmployee.js";
import { useI18n } from "@/i18n";

const { t, lang, resourceErrorMessage } = useI18n();
const { showToast } = useAppToast();
const { vehicle, stations, fuelRequests, grades, form, submitting, hasVehicle } = useEmployee();

const formError = ref("");

const vehicleMissing = computed(() => vehicle.state.status === "ready" && !hasVehicle.value);
const canSubmit = computed(
  () =>
    vehicle.state.status === "ready" &&
    hasVehicle.value &&
    stations.state.status === "ready" &&
    !submitting.value,
);
const stationsState = computed(() => {
  if (stations.state.status === "loading" || stations.state.status === "idle") return "loading";
  return stations.state.status === "error" ? "error" : "ready";
});
const fuelHistoryState = computed(() => {
  if (fuelRequests.state.status === "loading" || fuelRequests.state.status === "idle") return "loading";
  if (fuelRequests.state.status === "error") return "error";
  return fuelRequests.state.data.length ? "ready" : "empty";
});

const gradeOptions = computed(() =>
  grades.map((grade) => ({ label: t("fuelGrade." + grade), value: grade })),
);
const stationOptions = computed(() =>
  stations.state.data.map((station) => ({ label: station, value: station })),
);

onMounted(ensureStations);

async function onSubmit() {
  if (!canSubmit.value) return;
  formError.value = "";
  const result = await submitFuel();
  if (result.ok) {
    showToast(t("emp.fuel.sent"), "green");
    return;
  }
  if (!result.error) return;
  const message =
    result.error.messages?.[0] || resourceErrorMessage(result.error, "emp.fuel.error");
  formError.value = message;
  showToast(message, "red");
}
</script>
