<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("tickets.title") }}</h2>

    <!-- Raise a ticket -->
    <section class="card card-pad space-y-3">
      <p class="text-sm text-soft">{{ t("tickets.hint") }}</p>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="field-label">{{ t("tickets.category") }}</label>
          <!-- option VALUES stay English (sent to the API); only labels translate. -->
          <select v-model="form.category" class="select">
            <option v-for="c in categories" :key="c" :value="c">{{ te("issueCategory", c) }}</option>
          </select>
        </div>
        <div>
          <label class="field-label">{{ t("tickets.priority") }}</label>
          <select v-model="form.priority" class="select">
            <option v-for="p in priorities" :key="p" :value="p">{{ te("issuePriority", p) }}</option>
          </select>
        </div>
      </div>

      <div>
        <label class="field-label">{{ t("tickets.subject") }}</label>
        <input v-model="form.subject" :placeholder="t('tickets.subjectPlaceholder')" class="input" />
      </div>
      <div>
        <label class="field-label">{{ t("tickets.description") }}</label>
        <textarea v-model="form.description" :placeholder="t('tickets.descriptionPlaceholder')" class="textarea"></textarea>
      </div>

      <button class="btn btn-primary" :disabled="create.loading || !form.subject" @click="submit">
        <Icon name="help" :size="20" /> {{ t("tickets.raise") }}
      </button>
      <p v-if="err" class="text-sm text-danger">{{ err }}</p>
    </section>

    <!-- My tickets -->
    <section class="space-y-3">
      <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("tickets.myTickets") }}</h3>

      <LoadingState v-if="list.loading" :label="t('common.loading')" />

      <ErrorState v-else-if="list.error" :message="t('errors.loadFailed')" @retry="list.reload()" />

      <EmptyState v-else-if="!list.data || !list.data.length" icon="help" />

      <template v-else>
        <div v-for="t in list.data" :key="t.name" class="card card-pad">
          <div class="flex items-start justify-between gap-2">
            <div class="font-bold leading-tight">{{ t.subject }}</div>
            <span class="pill shrink-0" :class="statusPill(t.status)">{{ te("issueStatus", t.status) }}</span>
          </div>
          <div class="mt-1 text-sm text-muted">{{ te("issueCategory", t.category) }} · {{ te("issuePriority", t.priority) }}</div>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n, ISSUE_CATEGORIES, ISSUE_PRIORITIES } from "../i18n";

const { t, te } = useI18n();

const categories = ISSUE_CATEGORIES;
const priorities = ISSUE_PRIORITIES;

const err = ref("");
const form = reactive({ category: "Vehicle", priority: "Medium", subject: "", description: "" });

const list = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_support_tickets",
  auto: true,
});
const create = createResource({
  url: "apex_habitat.salis.api.driver_portal.raise_support_ticket",
  onSuccess: () => { form.subject = ""; form.description = ""; err.value = ""; list.reload(); },
  onError: (e) => { err.value = e.messages?.[0] || t("common.error"); },
});

function submit() {
  create.submit({ ...form });
}

// Map ticket status to a status pill (purely cosmetic).
function statusPill(status) {
  const s = (status || "").toLowerCase();
  if (s === "resolved" || s === "closed") return "pill-success";
  if (s === "waiting") return "pill-warning";
  if (s === "cancelled") return "pill-danger";
  return "pill-accent";
}
</script>
