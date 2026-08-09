<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <div v-if="submitted" class="card card-pad text-center space-y-3">
      <div class="avatar mx-auto h-12 w-12" style="background: var(--c-mint); color: var(--c-ink)">
        <Icon name="check" :size="26" />
      </div>
      <div>
        <p class="font-bold">{{ t("reqTransport.submitted") }}</p>
        <p class="text-sm text-muted mt-1">{{ t("reqTransport.submittedHint") }}</p>
      </div>
      <router-link to="/transport" class="btn btn-primary" style="text-decoration: none">
        <Icon name="route" :size="18" class="rtl-flip" /> {{ t("reqTransport.viewRequests") }}
      </router-link>
    </div>

    <form v-else class="space-y-5" @submit.prevent="submit">
      <p class="text-sm text-muted">{{ t("reqTransport.intro") }}</p>

      <section class="card card-pad form-ledger">
        <FormControl
          v-model="form.service_line"
          type="select"
          size="lg"
          :label="t('reqTransport.type')"
          :options="serviceOptions"
        />
        <FormControl
          v-model="form.from_location"
          type="text"
          size="lg"
          :label="t('reqTransport.from')"
          :placeholder="t('reqTransport.fromPlaceholder')"
        />
        <FormControl
          v-model="form.to_location"
          type="text"
          size="lg"
          :label="t('reqTransport.to')"
          :placeholder="t('reqTransport.toPlaceholder')"
        />
        <FormControl
          v-model="form.pickup_datetime"
          type="datetime-local"
          size="lg"
          :label="t('reqTransport.when')"
        />
        <FormControl
          v-model="form.purpose"
          type="textarea"
          size="lg"
          :rows="3"
          :label="t('reqTransport.reason')"
          :placeholder="t('reqTransport.reasonPlaceholder')"
        />
      </section>

      <section class="card card-pad space-y-3">
        <div class="flex items-center gap-2">
          <Icon name="user" :size="18" class="text-primary shrink-0" />
          <span class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("reqTransport.addPassengers") }}</span>
        </div>
        <p class="text-xs text-muted">{{ t("reqTransport.addPassengersHint") }}</p>

        <div v-for="(p, i) in form.adhoc_passengers" :key="i" class="adhoc-row">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-semibold text-muted">#{{ i + 1 }}</span>
            <Button
              type="button"
              variant="ghost"
              theme="red"
              size="md"
              :label="t('reqTransport.removeRow')"
              @click="removePassenger(i)"
            />
          </div>
          <FormControl v-model="p.full_name" type="text" size="lg" :label="t('reqTransport.passengerName')" />
          <div class="form-pair">
            <FormControl v-model="p.id_number" type="text" size="lg" :label="t('reqTransport.passengerId')" />
            <FormControl v-model="p.id_expiry" type="date" size="lg" :label="t('reqTransport.passengerExpiry')" />
          </div>
          <div class="form-pair">
            <FormControl v-model="p.nationality" type="text" size="lg" :label="t('reqTransport.passengerNationality')" />
            <FormControl v-model="p.phone" type="tel" size="lg" :label="t('reqTransport.passengerPhone')" />
          </div>
        </div>

        <Button type="button" variant="outline" size="xl" :label="t('reqTransport.addRow')" @click="addPassenger">
          <template #prefix><Icon name="plus" :size="18" /></template>
        </Button>
      </section>

      <p v-if="errorMsg" class="text-sm text-danger">{{ errorMsg }}</p>

      <Button
        type="submit"
        variant="solid"
        theme="green"
        size="2xl"
        :loading="create.loading"
        :loading-text="t('reqTransport.submitting')"
        :label="t('reqTransport.submit')"
      >
        <template #prefix><Icon name="send" :size="18" /></template>
      </Button>
    </form>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { Button, FormControl, createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import { useI18n, resourceErrorMessage } from "../i18n";

const { t } = useI18n();

const form = reactive({
  service_line: "Site Transport",
  from_location: "",
  to_location: "",
  pickup_datetime: "",
  purpose: "",
  adhoc_passengers: [],
});

const submitted = ref(false);
const errorMsg = ref("");

const serviceOptions = computed(() => [
  { label: t("reqTransport.typeSite"), value: "Site Transport" },
  { label: t("reqTransport.typeRelocation"), value: "Inter-City Relocation" },
]);

function addPassenger() {
  form.adhoc_passengers.push({ full_name: "", id_number: "", id_expiry: "", nationality: "", phone: "" });
}
function removePassenger(i) {
  form.adhoc_passengers.splice(i, 1);
}

const create = createResource({
  url: "apex.salis.api.masar.create_worker_transport_request",
  onSuccess: () => {
    submitted.value = true;
    errorMsg.value = "";
  },
  onError: (e) => {
    errorMsg.value = resourceErrorMessage(e, "reqTransport.failed");
  },
});

const passengersToSend = computed(() =>
  form.adhoc_passengers.filter((p) => (p.full_name || "").trim() && (p.id_number || "").trim()),
);

function submit() {
  errorMsg.value = "";
  if (!form.to_location.trim() && !form.purpose.trim()) {
    errorMsg.value = t("reqTransport.needDestination");
    return;
  }
  create.submit({
    service_line: form.service_line,
    from_location: form.from_location,
    to_location: form.to_location,
    pickup_datetime: form.pickup_datetime,
    purpose: form.purpose,
    adhoc_passengers: JSON.stringify(passengersToSend.value),
  });
}
</script>

<style scoped>
.adhoc-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-block-start: 1px solid var(--c-border);
  background: transparent;
}
</style>
