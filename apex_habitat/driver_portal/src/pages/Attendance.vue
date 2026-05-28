<template>
  <div class="space-y-4">
    <h2 class="font-semibold">Daily Attendance</h2>
    <button class="w-full bg-green-600 text-white rounded-xl p-4 disabled:opacity-50"
            :disabled="checkin.loading" @click="checkin.submit()">Check In</button>
    <button class="w-full bg-gray-700 text-white rounded-xl p-4 disabled:opacity-50"
            :disabled="checkout.loading" @click="checkout.submit()">Check Out</button>
    <p v-if="msg" class="text-center text-sm text-green-700">{{ msg }}</p>
    <p v-if="err" class="text-center text-sm text-red-600">{{ err }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { createResource } from "frappe-ui";

const msg = ref("");
const err = ref("");

const checkin = createResource({
  url: "apex_habitat.salis.api.driver_portal.driver_check_in",
  onSuccess: (r) => { msg.value = "Checked in at " + r.check_in; err.value = ""; },
  onError: (e) => { err.value = e.messages?.[0] || "Error"; },
});
const checkout = createResource({
  url: "apex_habitat.salis.api.driver_portal.driver_check_out",
  onSuccess: (r) => { msg.value = "Checked out at " + r.check_out; err.value = ""; },
  onError: (e) => { err.value = e.messages?.[0] || "Error"; },
});
</script>
