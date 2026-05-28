<template>
  <div class="space-y-4">
    <h2 class="font-semibold">Request Fuel</h2>
    <label class="block text-sm">Litres
      <input v-model.number="litres" type="number" min="1" class="mt-1 w-full border rounded-lg p-2" />
    </label>
    <button class="w-full bg-ah-warning text-white rounded-xl p-4 disabled:opacity-50"
            :disabled="req.loading || !litres" @click="submit">Submit Request</button>
    <p v-if="msg" class="text-center text-sm text-ah-primary">{{ msg }}</p>
    <p v-if="err" class="text-center text-sm text-ah-danger">{{ err }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { createResource } from "frappe-ui";

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
