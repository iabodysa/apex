<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("attendance.title") }}</h2>

    <section class="card card-pad space-y-3">
      <p class="text-sm text-soft">{{ t("attendance.hint") }}</p>
      <button class="btn btn-primary" :disabled="checkin.loading" @click="checkin.submit()">
        <Icon name="calendar" :size="20" /> {{ t("attendance.checkIn") }}
      </button>
      <button class="btn btn-dark" :disabled="checkout.loading" @click="checkout.submit()">
        <Icon name="calendar" :size="20" /> {{ t("attendance.checkOut") }}
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

const msg = ref("");
const err = ref("");

const checkin = createResource({
  url: "apex_habitat.salis.api.driver_portal.driver_check_in",
  onSuccess: (r) => { msg.value = t("attendance.checkedInAt", { time: r.check_in }); err.value = ""; },
  onError: (e) => { err.value = e.messages?.[0] || t("common.error"); },
});
const checkout = createResource({
  url: "apex_habitat.salis.api.driver_portal.driver_check_out",
  onSuccess: (r) => { msg.value = t("attendance.checkedOutAt", { time: r.check_out }); err.value = ""; },
  onError: (e) => { err.value = e.messages?.[0] || t("common.error"); },
});
</script>
