<template>
  <div class="space-y-5">
    <h2 class="section-title">Request Fuel</h2>

    <section class="card card-pad space-y-4">
      <div>
        <label class="field-label" for="fuel-litres">Litres</label>
        <input
          id="fuel-litres"
          v-model.number="litres"
          type="number"
          min="1"
          inputmode="numeric"
          placeholder="e.g. 40"
          class="input"
        />
      </div>
      <button class="btn btn-primary" :disabled="req.loading || !litres" @click="submit">
        <Icon name="fuel" :size="20" /> Submit Request
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

const litres = ref(null);
const msg = ref("");
const err = ref("");

const req = createResource({
  url: "apex_habitat.salis.api.driver_portal.submit_fuel_request",
  onSuccess: (r) => { msg.value = "Submitted: " + r.name; err.value = ""; litres.value = null; },
  onError: (e) => { err.value = e.messages?.[0] || "Error"; },
});

function submit() {
  req.submit({ litres: litres.value });
}
</script>
