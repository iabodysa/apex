<template>
  <div class="space-y-5">
    <h2 class="section-title">Daily Attendance</h2>

    <section class="card card-pad space-y-3">
      <p class="text-sm text-soft">Record your shift below. We stamp the time for you.</p>
      <button class="btn btn-primary" :disabled="checkin.loading" @click="checkin.submit()">
        <Icon name="calendar" :size="20" /> Check In
      </button>
      <button class="btn btn-dark" :disabled="checkout.loading" @click="checkout.submit()">
        <Icon name="calendar" :size="20" /> Check Out
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
