<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <!-- DETAIL: one ticket's SLA + conversation + reply (back returns to the list). -->
    <template v-if="selected">
      <button class="btn btn-outline" style="width: auto; padding-inline: 16px" @click="closeDetail">
        <Icon name="chevron" :size="18" /> {{ t("common.back") }}
      </button>

      <Skeleton v-if="detail.loading" :rows="4" />

      <ErrorState v-else-if="detail.error" :message="t('errors.loadFailed')" @retry="detail.reload()" />

      <template v-else-if="detail.data">
        <section class="card card-pad">
          <div class="flex items-start justify-between gap-2">
            <div class="font-bold leading-tight">{{ detail.data.subject }}</div>
            <span class="pill shrink-0" :class="statusPill(detail.data.status)">
              {{ te("issueStatus", detail.data.status) }}
            </span>
          </div>
          <div class="mt-1 text-sm text-muted">
            {{ te("issueCategory", detail.data.category) }} · {{ te("issuePriority", detail.data.priority) }}
          </div>
          <p v-if="detail.data.description" class="mt-3 text-sm whitespace-pre-line">{{ detail.data.description }}</p>

          <!-- Native SLA clock (response/resolution targets + when each was met). -->
          <dl class="mt-4 space-y-2 text-xs">
            <div v-if="detail.data.response_by" class="flex items-center gap-2">
              <Icon name="calendar" :size="14" class="text-primary shrink-0" />
              <dt class="text-muted">{{ t("tickets.respondBy") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ detail.data.response_by }}</bdi></dd>
            </div>
            <div v-if="detail.data.resolution_by" class="flex items-center gap-2">
              <Icon name="calendar" :size="14" class="text-primary shrink-0" />
              <dt class="text-muted">{{ t("tickets.resolveBy") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ detail.data.resolution_by }}</bdi></dd>
            </div>
            <div v-if="detail.data.first_responded_on" class="flex items-center gap-2 text-success">
              <Icon name="badge" :size="14" class="shrink-0" />
              <dt>{{ t("tickets.responded") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ detail.data.first_responded_on }}</bdi></dd>
            </div>
            <div v-if="detail.data.resolution_date" class="flex items-center gap-2 text-success">
              <Icon name="badge" :size="14" class="shrink-0" />
              <dt>{{ t("tickets.resolved") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ detail.data.resolution_date }}</bdi></dd>
            </div>
          </dl>
        </section>

        <!-- Conversation: native Communications, oldest first. -->
        <section class="space-y-3">
          <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("tickets.conversation") }}</h3>
          <p v-if="!detail.data.communications || !detail.data.communications.length" class="text-sm text-muted">
            {{ t("tickets.noReplies") }}
          </p>
          <div v-for="c in detail.data.communications" :key="c.name" class="card card-pad">
            <div class="flex items-center justify-between gap-2 text-xs text-muted">
              <span><bdi>{{ c.sender || t("tickets.you") }}</bdi></span>
              <span v-if="c.communication_date"><bdi>{{ c.communication_date }}</bdi></span>
            </div>
            <p v-if="c.content" class="mt-1 text-sm whitespace-pre-line">{{ c.content }}</p>
          </div>
        </section>

        <!-- Reply control (adds a native Communication; reopens a closed ticket). -->
        <section class="card card-pad space-y-3">
          <label class="field-label">{{ t("tickets.reply") }}</label>
          <textarea v-model="replyText" :placeholder="t('tickets.replyPlaceholder')" class="textarea"></textarea>
          <button class="btn btn-primary" :disabled="reply.loading || !replyText.trim()" @click="submitReply">
            <Icon name="help" :size="18" /> {{ t("tickets.send") }}
          </button>
        </section>
      </template>
    </template>

    <!-- LIST + raise (default view). -->
    <template v-else>
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

        <!-- Optional photo: camera-friendly on a phone, uploaded then attached. -->
        <div>
          <label class="field-label" for="ticket-photo">{{ t("tickets.attachment") }}</label>
          <input
            id="ticket-photo"
            type="file"
            accept="image/*"
            capture="environment"
            class="input"
            @change="onPhoto"
          />
          <p v-if="photoName" class="mt-1 text-xs text-success">{{ t("tickets.photoAttached") }}: {{ photoName }}</p>
        </div>

        <button class="btn btn-primary" :disabled="create.loading || uploading || !form.subject" @click="submit">
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
          <button
            v-for="row in list.data"
            :key="row.name"
            class="card card-pad block w-full text-start"
            @click="openDetail(row.name)"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="font-bold leading-tight">{{ row.subject }}</div>
              <span class="pill shrink-0" :class="statusPill(row.status)">{{ te("issueStatus", row.status) }}</span>
            </div>
            <div class="mt-1 flex items-center gap-2 text-sm text-muted">
              <span>{{ te("issueCategory", row.category) }} · {{ te("issuePriority", row.priority) }}</span>
              <Icon name="chevron" :size="16" class="ms-auto shrink-0" />
            </div>
          </button>
        </template>
      </section>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import Skeleton from "../components/Skeleton.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n, ISSUE_CATEGORIES, ISSUE_PRIORITIES } from "../i18n";
import { pushToast } from "../toast";

const { t, te } = useI18n();

const categories = ISSUE_CATEGORIES;
const priorities = ISSUE_PRIORITIES;

const err = ref("");
const form = reactive({ category: "Vehicle", priority: "Medium", subject: "", description: "" });

// Uploaded-photo url (set after upload) + its file name for the confirmation line.
const attachment = ref(null);
const photoName = ref("");
const uploading = ref(false);

const list = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_support_tickets",
  auto: true,
});
const create = createResource({
  url: "apex_habitat.salis.api.driver_portal.raise_support_ticket",
  onSuccess: () => {
    form.subject = "";
    form.description = "";
    attachment.value = null;
    photoName.value = "";
    err.value = "";
    list.reload();
  },
  onError: (e) => { err.value = e.messages?.[0] || t("common.error"); },
});

// Upload the chosen image first (native upload_file), keep its url to attach on raise.
async function onPhoto(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  uploading.value = true;
  try {
    const fd = new FormData();
    fd.append("file", file, file.name);
    fd.append("is_private", 1);
    const res = await fetch("/api/method/upload_file", {
      method: "POST",
      headers: { "X-Frappe-CSRF-Token": window.csrf_token },
      body: fd,
    });
    const json = await res.json();
    attachment.value = json.message?.file_url || null;
    photoName.value = attachment.value ? file.name : "";
  } catch (_e) {
    pushToast(t("common.error"), "err");
  } finally {
    uploading.value = false;
  }
}

function submit() {
  create.submit({ ...form, attachment: attachment.value });
}

// --- Ticket detail (get_ticket) + reply (reply_to_ticket). ---
const selected = ref(null);
const replyText = ref("");

const detail = createResource({
  url: "apex_habitat.salis.api.driver_portal.get_ticket",
  makeParams: () => ({ name: selected.value }),
});

function openDetail(name) {
  selected.value = name;
  replyText.value = "";
  detail.fetch();
}
function closeDetail() {
  selected.value = null;
  list.reload(); // a reply may have reopened a ticket; refresh the list status
}

const reply = createResource({
  url: "apex_habitat.salis.api.driver_portal.reply_to_ticket",
  onSuccess: () => { replyText.value = ""; pushToast(t("tickets.replySent"), "ok"); detail.reload(); },
  onError: (e) => pushToast(e.messages?.[0] || t("common.error"), "err"),
});
function submitReply() {
  if (!replyText.value.trim()) return;
  reply.submit({ name: selected.value, message: replyText.value.trim() });
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
