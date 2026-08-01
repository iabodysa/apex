<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <!-- DETAIL: one ticket's SLA + conversation + reply (back returns to the list). -->
    <template v-if="selected">
      <button class="btn btn-outline" style="width: auto; padding-inline: 16px" @click="closeDetail">
        <Icon name="chevron" :size="18" /> {{ t("common.back") }}
      </button>

      <Skeleton v-if="detailLoading" :rows="4" />

      <ErrorState v-else-if="detailError" :message="t('errors.loadFailed')" @retry="loadTicketDetail" />

      <template v-else-if="detailData">
        <section class="card card-pad">
          <div class="flex items-start justify-between gap-2">
            <div class="font-bold leading-tight">{{ detailData.subject }}</div>
            <span class="pill shrink-0" :class="statusPill(detailData.status)">
              {{ te("issueStatus", detailData.status) }}
            </span>
          </div>
          <div class="mt-1 text-sm text-muted">
            {{ te("issueCategory", detailData.category) }} · {{ te("issuePriority", detailData.priority) }}
          </div>
          <p v-if="detailData.description" class="mt-3 text-sm whitespace-pre-line">{{ detailData.description }}</p>

          <!-- Native SLA clock (response/resolution targets + when each was met). -->
          <dl class="mt-4 space-y-2 text-xs">
            <div v-if="detailData.response_by" class="flex items-center gap-2">
              <Icon name="calendar" :size="14" class="text-primary shrink-0" />
              <dt class="text-muted">{{ t("tickets.respondBy") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ detailData.response_by }}</bdi></dd>
            </div>
            <div v-if="detailData.resolution_by" class="flex items-center gap-2">
              <Icon name="calendar" :size="14" class="text-primary shrink-0" />
              <dt class="text-muted">{{ t("tickets.resolveBy") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ detailData.resolution_by }}</bdi></dd>
            </div>
            <div v-if="detailData.first_responded_on" class="flex items-center gap-2 text-success">
              <Icon name="badge" :size="14" class="shrink-0" />
              <dt>{{ t("tickets.responded") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ detailData.first_responded_on }}</bdi></dd>
            </div>
            <div v-if="detailData.resolution_date" class="flex items-center gap-2 text-success">
              <Icon name="badge" :size="14" class="shrink-0" />
              <dt>{{ t("tickets.resolved") }}</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ detailData.resolution_date }}</bdi></dd>
            </div>
          </dl>
        </section>

        <!-- Conversation: native Communications, oldest first. -->
        <section class="space-y-3">
          <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("tickets.conversation") }}</h3>
          <p v-if="!communications.length" class="text-sm text-muted">
            {{ t("tickets.noReplies") }}
          </p>
          <div v-for="c in communications" :key="c.name" class="card card-pad">
            <div class="flex items-center justify-between gap-2 text-xs text-muted">
              <span><bdi>{{ c.sender || t("tickets.you") }}</bdi></span>
              <span v-if="c.communication_date"><bdi>{{ c.communication_date }}</bdi></span>
            </div>
            <p v-if="c.content" class="mt-1 text-sm whitespace-pre-line">{{ c.content }}</p>
          </div>
          <button
            v-if="communicationHasMore"
            class="btn btn-outline w-full"
            :disabled="moreLoading"
            @click="loadMoreCommunications"
          >
            {{ moreLoading ? t("common.loading") : t("common.more") }}
          </button>
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

        <!-- Optional photo: read locally and attached by the ticket POST. -->
        <div>
          <label class="field-label" for="ticket-photo">{{ t("tickets.attachment") }}</label>
          <input
            id="ticket-photo"
            type="file"
            :accept="PHOTO_ACCEPT"
            capture="environment"
            class="input"
            @change="onPhoto"
          />
          <p v-if="photoError" class="mt-1 text-xs text-danger">{{ photoError }}</p>
          <p v-else-if="photoName" class="mt-1 text-xs text-success">{{ t("tickets.photoAttached") }}: {{ photoName }}</p>
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
import { readPhotoFile, UnsupportedPhotoType } from "../upload";
import { PHOTO_ACCEPT } from "@shared/photoFile.js";
import { isCurrentTicketRequest, mergeCommunicationPages } from "../ticketPagination";

const { t, te } = useI18n();

const categories = ISSUE_CATEGORIES;
const priorities = ISSUE_PRIORITIES;

const err = ref("");
const form = reactive({ category: "Vehicle", priority: "Medium", subject: "", description: "" });

// Inline photo payload for the existing credential-scoped ticket POST.
const photo = ref({ photo: null, photo_filename: null });
const photoName = ref("");
const photoError = ref("");
const uploading = ref(false);

const list = createResource({
  url: "apex.salis.api.driver_portal.my_support_tickets",
  auto: true,
});
const create = createResource({
  url: "apex.salis.api.driver_portal.raise_support_ticket",
  onSuccess: () => {
    form.subject = "";
    form.description = "";
    photo.value = { photo: null, photo_filename: null };
    photoName.value = "";
    photoError.value = "";
    err.value = "";
    list.reload();
  },
  onError: (e) => { err.value = e.messages?.[0] || t("common.error"); },
});

// Read the chosen image locally; the ticket POST creates its private attachment.
async function onPhoto(e) {
  const file = e.target.files && e.target.files[0];
  // Reset the input so re-picking the same file re-fires change after a refusal.
  e.target.value = "";
  if (!file) return;
  uploading.value = true;
  photoError.value = "";
  try {
    photo.value = await readPhotoFile(file);
    photoName.value = photo.value.photo ? file.name : "";
  } catch (err_) {
    photo.value = { photo: null, photo_filename: null };
    photoName.value = "";
    // Name the accepted formats rather than a generic failure.
    photoError.value =
      err_ instanceof UnsupportedPhotoType ? t("tickets.photoType") : t("common.error");
    pushToast(photoError.value, "err");
  } finally {
    uploading.value = false;
  }
}

function submit() {
  create.submit({ ...form, ...photo.value });
}

// --- Ticket detail (get_ticket) + reply (reply_to_ticket). ---
const selected = ref(null);
const replyText = ref("");
const communications = ref([]);
const communicationHasMore = ref(false);
const communicationNextOffset = ref(null);
const communicationPageLimit = 20;
const ticketGeneration = ref(0);
const detailData = ref(null);
const detailLoading = ref(false);
const detailError = ref(null);
const moreLoading = ref(false);

function activeTicketRequest() {
  return { ticket: selected.value, generation: ticketGeneration.value };
}

function applyCommunicationPage(data, replace = false) {
  communications.value = mergeCommunicationPages(
    replace ? [] : communications.value,
    data.communications || [],
  );
  communicationHasMore.value = Boolean(data.communication_has_more);
  communicationNextOffset.value = data.communication_next_offset;
}

const detail = createResource({
  url: "apex.salis.api.driver_portal.get_ticket",
});

const moreCommunications = createResource({
  url: "apex.salis.api.driver_portal.get_ticket",
});

function resetDetailState() {
  communications.value = [];
  communicationHasMore.value = false;
  communicationNextOffset.value = null;
  detailData.value = null;
  detailError.value = null;
  moreLoading.value = false;
}
function loadTicketDetail() {
  const requested = activeTicketRequest();
  detailLoading.value = true;
  detailError.value = null;
  detail.fetch(
    {
      name: requested.ticket,
      communication_offset: 0,
      communication_limit: communicationPageLimit,
    },
    {
      onSuccess: (data) => {
        if (!isCurrentTicketRequest(requested, activeTicketRequest())) return;
        detailData.value = data;
        applyCommunicationPage(data, true);
        detailLoading.value = false;
      },
      onError: (error) => {
        if (!isCurrentTicketRequest(requested, activeTicketRequest())) return;
        detailError.value = error;
        detailLoading.value = false;
      },
    },
  );
}
function openDetail(name) {
  ticketGeneration.value += 1;
  selected.value = name;
  replyText.value = "";
  resetDetailState();
  loadTicketDetail();
}
function loadMoreCommunications() {
  if (
    !communicationHasMore.value
    || communicationNextOffset.value == null
    || moreLoading.value
  ) return;
  const requested = activeTicketRequest();
  const offset = communicationNextOffset.value;
  moreLoading.value = true;
  moreCommunications.fetch(
    {
      name: requested.ticket,
      communication_offset: offset,
      communication_limit: communicationPageLimit,
    },
    {
      onSuccess: (data) => {
        if (!isCurrentTicketRequest(requested, activeTicketRequest())) return;
        applyCommunicationPage(data);
        moreLoading.value = false;
      },
      onError: (error) => {
        if (!isCurrentTicketRequest(requested, activeTicketRequest())) return;
        moreLoading.value = false;
        pushToast(error.messages?.[0] || t("common.error"), "err");
      },
    },
  );
}
function closeDetail() {
  ticketGeneration.value += 1;
  selected.value = null;
  detailLoading.value = false;
  resetDetailState();
  list.reload(); // a reply may have reopened a ticket; refresh the list status
}

const reply = createResource({
  url: "apex.salis.api.driver_portal.reply_to_ticket",
});
function submitReply() {
  if (!replyText.value.trim()) return;
  const requested = activeTicketRequest();
  reply.submit(
    { name: requested.ticket, message: replyText.value.trim() },
    {
      onSuccess: () => {
        if (!isCurrentTicketRequest(requested, activeTicketRequest())) return;
        replyText.value = "";
        pushToast(t("tickets.replySent"), "ok");
        ticketGeneration.value += 1;
        resetDetailState();
        loadTicketDetail();
      },
      onError: (error) => {
        if (!isCurrentTicketRequest(requested, activeTicketRequest())) return;
        pushToast(error.messages?.[0] || t("common.error"), "err");
      },
    },
  );
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
