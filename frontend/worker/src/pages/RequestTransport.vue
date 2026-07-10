<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("reqTransport.title") }}</h2>

    <!-- Success state: the request was created; offer to view the worker's trips. -->
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

      <section class="card card-pad space-y-4">
        <div>
          <label class="field-label" for="rt-type">{{ t("reqTransport.type") }}</label>
          <select id="rt-type" v-model="form.service_line" class="select">
            <option value="Site Transport">{{ t("reqTransport.typeSite") }}</option>
            <option value="Inter-City Relocation">{{ t("reqTransport.typeRelocation") }}</option>
          </select>
        </div>

        <div>
          <label class="field-label" for="rt-from">{{ t("reqTransport.from") }}</label>
          <input id="rt-from" v-model="form.from_location" class="input" :placeholder="t('reqTransport.fromPlaceholder')" />
        </div>

        <div>
          <label class="field-label" for="rt-to">{{ t("reqTransport.to") }}</label>
          <input id="rt-to" v-model="form.to_location" class="input" :placeholder="t('reqTransport.toPlaceholder')" />
        </div>

        <div>
          <label class="field-label" for="rt-when">{{ t("reqTransport.when") }}</label>
          <input id="rt-when" v-model="form.pickup_datetime" type="datetime-local" class="input" />
        </div>

        <div>
          <label class="field-label" for="rt-reason">{{ t("reqTransport.reason") }}</label>
          <textarea id="rt-reason" v-model="form.purpose" class="textarea" rows="3" :placeholder="t('reqTransport.reasonPlaceholder')"></textarea>
        </div>
      </section>

      <!-- Ad-hoc (unregistered) co-passengers. Each row is a name + ID (+ optional
           expiry/nationality/phone); kept distinct from registered workers (the
           worker themself is always added server-side). -->
      <section class="card card-pad space-y-3">
        <div class="flex items-center gap-2">
          <Icon name="user" :size="18" class="text-primary shrink-0" />
          <span class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("reqTransport.addPassengers") }}</span>
        </div>
        <p class="text-xs text-muted">{{ t("reqTransport.addPassengersHint") }}</p>

        <div v-for="(p, i) in form.adhoc_passengers" :key="i" class="adhoc-row">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-semibold text-muted">#{{ i + 1 }}</span>
            <button type="button" class="text-xs text-danger" @click="removePassenger(i)">
              {{ t("reqTransport.removeRow") }}
            </button>
          </div>
          <input v-model="p.full_name" class="input" :placeholder="t('reqTransport.passengerName')" />
          <div class="grid grid-cols-2 gap-2">
            <input v-model="p.id_number" class="input" :placeholder="t('reqTransport.passengerId')" />
            <input v-model="p.id_expiry" type="date" class="input" :aria-label="t('reqTransport.passengerExpiry')" />
          </div>
          <div class="grid grid-cols-2 gap-2">
            <input v-model="p.nationality" class="input" :placeholder="t('reqTransport.passengerNationality')" />
            <input v-model="p.phone" class="input" :placeholder="t('reqTransport.passengerPhone')" />
          </div>
        </div>

        <button type="button" class="btn btn-outline" style="width: auto; padding-inline: 18px" @click="addPassenger">
          <Icon name="plus" :size="18" /> {{ t("reqTransport.addRow") }}
        </button>
      </section>

      <p v-if="errorMsg" class="text-sm text-danger">{{ errorMsg }}</p>

      <button type="submit" class="btn btn-primary" :disabled="create.loading">
        <Icon name="send" :size="18" />
        {{ create.loading ? t("reqTransport.submitting") : t("reqTransport.submit") }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { TOKEN } from "../utils/token";

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

// Only send ad-hoc rows the worker actually filled (a name + ID); blank rows are
// dropped client-side so an empty extra row never trips the server validation.
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
    token: TOKEN,
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
  border-radius: var(--radius, 12px);
  background: color-mix(in srgb, var(--c-ink) 4%, transparent);
}
</style>
