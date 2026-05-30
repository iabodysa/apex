<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("requests.title") }}</h2>

    <!-- Raise a request -->
    <section class="card card-pad space-y-3">
      <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("requests.new") }}</h3>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="field-label">{{ t("requests.category") }}</label>
          <!-- option VALUES stay English (sent to the API); only labels translate. -->
          <select v-model="form.category" class="select">
            <option value="Maintenance">{{ t("requests.catMaintenance") }}</option>
            <option value="Cleaning">{{ t("requests.catCleaning") }}</option>
            <option value="AC">{{ t("requests.catAC") }}</option>
            <option value="Plumbing">{{ t("requests.catPlumbing") }}</option>
            <option value="Electrical">{{ t("requests.catElectrical") }}</option>
            <option value="Water">{{ t("requests.catWater") }}</option>
            <option value="Pest Control">{{ t("requests.catPestControl") }}</option>
            <option value="Custody">{{ t("requests.catCustody") }}</option>
            <option value="Complaint">{{ t("requests.catComplaint") }}</option>
            <option value="Suggestion">{{ t("requests.catSuggestion") }}</option>
            <option value="Other">{{ t("requests.catOther") }}</option>
          </select>
        </div>
        <div>
          <label class="field-label">{{ t("requests.priority") }}</label>
          <select v-model="form.priority" class="select">
            <option value="Low">{{ t("requests.prioLow") }}</option>
            <option value="Medium">{{ t("requests.prioMedium") }}</option>
            <option value="High">{{ t("requests.prioHigh") }}</option>
            <option value="Critical">{{ t("requests.prioCritical") }}</option>
          </select>
        </div>
      </div>

      <div>
        <label class="field-label">{{ t("requests.subject") }}</label>
        <input v-model="form.subject" :placeholder="t('requests.subjectPlaceholder')" class="input" />
      </div>
      <div>
        <label class="field-label">{{ t("requests.description") }}</label>
        <textarea v-model="form.body" :placeholder="t('requests.descriptionPlaceholder')" class="textarea"></textarea>
      </div>

      <button class="btn btn-primary" :disabled="create.loading || !canSubmit" @click="submit">
        <Icon name="send" :size="20" /> {{ t("requests.submit") }}
      </button>
      <p v-if="ok" class="status-note status-ok">{{ t("requests.submitted") }}</p>
      <p v-if="err" class="status-note status-err">{{ err }}</p>
    </section>

    <!-- My requests -->
    <section v-if="list.data && list.data.length" class="space-y-3">
      <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("requests.mine") }}</h3>
      <div v-for="r in list.data" :key="r.name" class="card card-pad">
        <div class="flex items-start justify-between gap-2">
          <div class="font-bold leading-tight">{{ r.request_category }}</div>
          <span class="pill shrink-0" :class="statusPill(r.status)">{{ r.status }}</span>
        </div>
        <p class="mt-1 text-sm text-soft whitespace-pre-line line-clamp-3">{{ r.description }}</p>
        <div class="mt-1 text-xs text-muted">{{ r.priority }} · {{ formatDate(r.creation) }}</div>
        <div v-if="r.resolution_notes" class="mt-2 text-sm">
          <span class="text-muted">{{ t("requests.resolution") }}:</span>
          <span class="font-semibold"> {{ r.resolution_notes }}</span>
        </div>
      </div>
    </section>

    <div v-else-if="!list.loading" class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("requests.empty") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";
import { TOKEN } from "../token";

const { t } = useI18n();

const ok = ref(false);
const err = ref("");
const form = reactive({ category: "Maintenance", priority: "Low", subject: "", body: "" });

const canSubmit = computed(() => !!(form.subject.trim() || form.body.trim()));

const list = createResource({
  url: "apex_habitat.salis.api.masar.list_worker_requests",
  params: { token: TOKEN },
  auto: true,
});

const create = createResource({
  url: "apex_habitat.salis.api.masar.create_worker_request",
  onSuccess: () => {
    form.subject = "";
    form.body = "";
    err.value = "";
    ok.value = true;
    setTimeout(() => (ok.value = false), 3000);
    list.reload();
  },
  onError: (e) => {
    ok.value = false;
    err.value = e.messages?.[0] || t("common.error");
  },
});

function submit() {
  ok.value = false;
  err.value = "";
  create.submit({
    token: TOKEN,
    category: form.category,
    priority: form.priority,
    subject: form.subject,
    body: form.body,
  });
}

function statusPill(status) {
  const s = (status || "").toLowerCase();
  if (s === "resolved" || s === "closed") return "pill-success";
  if (s === "in progress" || s === "assigned" || s === "triaged") return "pill-warning";
  if (s === "rejected") return "pill-danger";
  return "pill-accent";
}

function formatDate(c) {
  return (c || "").slice(0, 10);
}
</script>
