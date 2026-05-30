<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("fuel.title") }}</h2>

    <section class="card card-pad space-y-4">
      <div>
        <label class="field-label" for="fuel-litres">{{ t("fuel.litres") }}</label>
        <input
          id="fuel-litres"
          v-model.number="litres"
          type="number"
          min="1"
          inputmode="numeric"
          :placeholder="t('fuel.placeholder')"
          class="input"
        />
      </div>
      <button class="btn btn-primary" :disabled="req.loading || !litres" @click="submit">
        <Icon name="fuel" :size="20" /> {{ t("fuel.submit") }}
      </button>
    </section>

    <p v-if="msg" class="status-note status-ok">{{ msg }}</p>
    <p v-if="err" class="status-note status-err">{{ err }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const litres = ref(null);
const msg = ref("");
const err = ref("");

const req = createResource({
  url: "apex_habitat.salis.api.driver_portal.submit_fuel_request",
  onSuccess: (r) => { msg.value = t("fuel.submitted", { name: r.name }); err.value = ""; litres.value = null; },
  onError: (e) => { err.value = e.messages?.[0] || t("common.error"); },
});

function submit() {
  req.submit({ litres: litres.value });
}
</script>
