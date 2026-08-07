<!-- Copyright (c) 2026, afmcoltd -->
<script setup>
import { ref, onMounted } from "vue";
import Icon from "../components/Icon.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import { useI18n } from "../i18n";
import { useToast } from "@shared/useToast.js";
import { useEmployee, fetchFuelRequests } from "../useEmployee.js";
import { fuelMetaFor } from "../fuelMeta.js";

const { t } = useI18n();
const { toast, showToast } = useToast();
const { fuelGrades, stations, form, submitting, loading, loadError, reload, submitFuelRequest } =
  useEmployee();

const formError = ref("");

const history = ref([]);
const historyLoading = ref(true);
const historyError = ref(false);

async function loadHistory() {
  historyLoading.value = true;
  historyError.value = false;
  try {
    history.value = await fetchFuelRequests();
  } catch (e) {
    historyError.value = true;
  } finally {
    historyLoading.value = false;
  }
}
onMounted(loadHistory);

async function onSubmit() {
  if (submitting.value) return;
  formError.value = "";
  try {
    const res = await submitFuelRequest();
    if (res && res.ok) showToast(t("emp.fuel.sent"), "green");
  } catch (e) {
    const msg = (e && (e.messages?.[0] || e.message)) || t("emp.fuel.error");
    formError.value = msg;
    showToast(msg, "red");
  }
}
</script>

<template>
  <div class="emp-narrow">
    <section class="emp-card reveal d1">
      <p v-if="loading" class="emp-empty">{{ t("emp.loading") }}</p>
      <div v-else-if="loadError && !stations.length" class="emp-fail">
        <p>{{ t("emp.loadError") }}</p>
        <button type="button" class="emp-btn emp-btn-ghost emp-retry" @click="reload">
          <Icon name="rotate-cw" :size="15" />{{ t("common.retry") }}
        </button>
      </div>
      <form v-else @submit.prevent="onSubmit">
        <div class="emp-field">
          <label for="ff-grade">{{ t("emp.fuel.fuelType") }}</label>
          <div class="emp-select-wrap">
            <select id="ff-grade" v-model="form.fuelGrade" class="emp-control">
              <option v-for="g in fuelGrades" :key="g" :value="g">{{ t("fuelGrade." + g) }}</option>
            </select>
            <Icon class="emp-select-caret" name="chevron" :size="15" />
          </div>
        </div>

        <div class="emp-field">
          <label for="ff-litres">{{ t("emp.fuel.quantity") }}</label>
          <div class="emp-control emp-control-num">
            <input id="ff-litres" v-model.number="form.litres" type="number" min="1" step="1" inputmode="numeric" />
            <span class="emp-unit">{{ t("emp.fuel.litresUnit") }}</span>
          </div>
        </div>

        <div class="emp-field">
          <label for="ff-station">{{ t("emp.fuel.station") }}</label>
          <div class="emp-select-wrap">
            <select id="ff-station" v-model="form.station" class="emp-control">
              <option v-for="s in stations" :key="s" :value="s">{{ s }}</option>
            </select>
            <Icon class="emp-select-caret" name="chevron" :size="15" />
          </div>
        </div>

        <div class="emp-field">
          <label for="ff-notes">{{ t("emp.fuel.notes") }}</label>
          <textarea
            id="ff-notes"
            v-model="form.notes"
            class="emp-control emp-textarea"
            rows="2"
            :placeholder="t('emp.fuel.notesPlaceholder')"
          ></textarea>
        </div>

        <p v-if="formError" id="ff-error" class="emp-form-error" role="alert">
          <Icon name="triangle-alert" :size="15" />
          {{ formError }}
        </p>

        <button
          type="submit"
          class="emp-btn emp-btn-primary"
          :disabled="submitting"
          :aria-describedby="formError ? 'ff-error' : undefined"
        >
          <Icon v-if="!submitting" name="rotate-cw" :size="17" />
          {{ submitting ? t("emp.fuel.sending") : t("emp.fuel.submit") }}
        </button>
      </form>
    </section>

    <section class="emp-card reveal d2">
      <h3 class="emp-card-title">{{ t("emp.fuel.history") }}</h3>
      <p v-if="historyLoading" class="emp-empty">{{ t("emp.loading") }}</p>
      <div v-else-if="historyError" class="emp-fail">
        <p>{{ t("emp.loadError") }}</p>
        <button type="button" class="emp-btn emp-btn-ghost emp-retry" @click="loadHistory">
          <Icon name="rotate-cw" :size="15" />{{ t("common.retry") }}
        </button>
      </div>
      <EmptyState v-else-if="!history.length" :title="t('emp.fuel.historyEmpty')">
        <template #icon><Icon name="clipboard-list" :size="20" /></template>
      </EmptyState>
      <ul v-else class="emp-trips">
        <li v-for="row in history" :key="row.name" class="emp-trip">
          <span class="emp-pill" :class="fuelMetaFor(row.statusKey).cls">
            <span class="dot"></span>{{ t(fuelMetaFor(row.statusKey).key) }}
          </span>
          <div class="emp-route">
            <b>{{ row.litres }} {{ t("emp.fuel.litresUnit") }}</b>
            <span>
              <template v-if="row.date">{{ row.date }}</template>
              <template v-if="row.station"> · {{ row.station }}</template>
              <template v-if="row.vehicle"> · {{ row.vehicle }}</template>
            </span>
          </div>
        </li>
      </ul>
    </section>
  </div>

  <div class="toast" :class="[toast.show ? 'show' : '', 'toast-' + toast.type]">{{ toast.msg }}</div>
</template>
