<!-- Copyright (c) 2026, AFMCO and contributors -->
<script setup>
/*
 * FUEL — the fuel-request form as its own page. The page title and hint are
 * the shell heading (App.vue), so the card carries only the form.
 *
 * No request-history list here YET: apex.salis.api.fleet_employee exposes no
 * employee-scoped fuel-request read (driver_portal.fuel.my_fuel_requests is
 * the credential-first barcode surface, gated on the driver-portal flag, so it
 * is not this session portal's endpoint). The list ships when the backend does.
 */
import { ref } from "vue";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";
import { useToast } from "@shared/useToast.js";
import { useEmployee } from "../useEmployee.js";

const { t } = useI18n();
const { toast, showToast } = useToast();
const { fuelGrades, stations, form, submitting, loading, loadError, reload, submitFuelRequest } =
  useEmployee();

// The server's rejection reason names the limit that was exceeded, so it is held
// on the form until the next attempt rather than only flashed in a toast.
const formError = ref("");

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
      <!-- Same [#emp-fail] rule as the home cards: a broken stations load must
           not render a silently empty select. Gated on the list being empty, so
           stations that did load keep the form usable when only a sibling
           request failed. -->
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

        <!-- The rejection reason names a limit the employee has to act on, so it
             stays on the form next to the field that caused it. The toast alone
             took it away after three seconds. -->
        <p v-if="formError" id="ff-error" class="emp-form-error" role="alert">
          <Icon name="triangle-alert" :size="15" />
          {{ formError }}
        </p>

        <!-- No "Save as draft" here. The control that used to sit below this one
             raised a "Saved as a draft" toast and made no call at all, so a
             request the employee believed was kept was silently discarded. A
             draft needs somewhere to be stored before it can be offered. -->
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
  </div>

  <!-- TOAST -->
  <div class="toast" :class="[toast.show ? 'show' : '', 'toast-' + toast.type]">{{ toast.msg }}</div>
</template>
