<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <template v-if="selected">
      <Button variant="outline" size="xl" :label="t('common.back')" @click="closeDetail">
        <template #prefix><Icon name="chevron" :size="18" /></template>
      </Button>

      <Skeleton v-if="detailLoading" :rows="4" />

      <LoadError
        v-else-if="detailError"
        :title="t('errors.loadFailed')"
        :detail="detailErrorMessage"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="loadTicketDetail"
      />

      <template v-else-if="detailData">
        <section class="card card-pad">
          <div class="flex items-start justify-between gap-2">
            <div class="font-bold leading-tight">{{ detailData.subject }}</div>
            <StatusLabel
              class="shrink-0"
              :label="te('issueStatus', detailData.status)"
              :tone="statusTone(detailData.status)"
            />
          </div>
          <div class="mt-1 text-sm text-muted">
            {{ te("issueCategory", detailData.category) }} · {{ te("issuePriority", detailData.priority) }}
          </div>
          <p v-if="detailData.description" class="mt-3 text-sm whitespace-pre-line">{{ detailData.description }}</p>

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

        <Panel :title="t('tickets.conversation')">
          <EmptyState v-if="!communications.length" :title="t('tickets.noReplies')">
            <template #icon><Icon name="help" :size="22" /></template>
          </EmptyState>
          <div v-for="c in communications" :key="c.name" class="card card-pad">
            <div class="flex items-center justify-between gap-2 text-xs text-muted">
              <span><bdi>{{ c.sender || t("tickets.you") }}</bdi></span>
              <span v-if="c.communication_date"><bdi>{{ c.communication_date }}</bdi></span>
            </div>
            <p v-if="c.content" class="mt-1 text-sm whitespace-pre-line">{{ c.content }}</p>
          </div>
          <Button
            v-if="communicationHasMore"
            class="mt-3"
            variant="outline"
            size="xl"
            :disabled="moreLoading"
            :loading="moreLoading"
            :label="t('common.more')"
            @click="loadMoreCommunications"
          />
        </Panel>

        <section class="card card-pad">
          <FormControl v-model="replyText" type="textarea" size="lg" :rows="4" :label="t('tickets.reply')" :placeholder="t('tickets.replyPlaceholder')" />
        </section>

        <ActionDock>
          <template #primary>
            <Button
              class="dock-btn"
              variant="solid"
              theme="green"
              size="2xl"
              :disabled="reply.loading || !replyText.trim()"
              :loading="reply.loading"
              :label="t('tickets.send')"
              @click="submitReply"
            >
              <template #prefix><Icon name="help" :size="20" /></template>
            </Button>
          </template>
        </ActionDock>
      </template>
    </template>

    <template v-else>
      <section class="card card-pad space-y-3">
        <p class="text-sm text-soft">{{ t("tickets.hint") }}</p>

        <div class="form-pair">
          <FormControl v-model="form.category" type="select" size="lg" :label="t('tickets.category')" :options="categoryOptions" />
          <FormControl v-model="form.priority" type="select" size="lg" :label="t('tickets.priority')" :options="priorityOptions" />
        </div>

        <FormControl v-model="form.subject" type="text" size="lg" :label="t('tickets.subject')" :placeholder="t('tickets.subjectPlaceholder')" />
        <FormControl v-model="form.description" type="textarea" size="lg" :rows="4" :label="t('tickets.description')" :placeholder="t('tickets.descriptionPlaceholder')" />

        <div>
          <label class="field-label" for="ticket-photo">{{ t("tickets.attachment") }}</label>
          <input
            ref="photoInput"
            id="ticket-photo"
            type="file"
            :accept="PHOTO_ACCEPT"
            capture="environment"
            class="visually-hidden"
            @change="onPhoto"
          />
          <Button variant="outline" size="xl" :loading="uploading" :label="photoName || t('tickets.addPhoto')" @click="choosePhoto">
            <template #prefix><Icon name="image" :size="18" /></template>
          </Button>
          <p v-if="photoError" class="mt-1 text-xs text-danger">{{ photoError }}</p>
          <p v-else-if="photoName" class="mt-1 text-xs text-success">{{ t("tickets.photoAttached") }}: {{ photoName }}</p>
        </div>

        <p v-if="err" class="text-sm text-danger">{{ err }}</p>
      </section>

      <Panel :title="t('tickets.myTickets')">
        <LoadingState v-if="list.loading" :label="t('common.loading')" />

        <LoadError
          v-else-if="list.error"
          :title="t('errors.loadFailed')"
          :detail="listErrorMessage"
          :hint="t('errors.retryHint')"
          :retry-label="t('common.retry')"
          @retry="list.reload()"
        />

        <EmptyState
          v-else-if="!list.data || !list.data.length"
          :title="t('tickets.empty')"
          :hint="t('tickets.emptyHint')"
        >
          <template #icon><Icon name="help" :size="22" /></template>
        </EmptyState>

        <template v-else>
          <button
            v-for="row in list.data"
            :key="row.name"
            class="card card-pad block w-full text-start"
            @click="openDetail(row.name)"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="font-bold leading-tight">{{ row.subject }}</div>
              <StatusLabel class="shrink-0" :label="te('issueStatus', row.status)" :tone="statusTone(row.status)" />
            </div>
            <div class="mt-1 flex items-center gap-2 text-sm text-muted">
              <span>{{ te("issueCategory", row.category) }} · {{ te("issuePriority", row.priority) }}</span>
              <Icon name="chevron" :size="16" class="ms-auto shrink-0" />
            </div>
          </button>
        </template>
      </Panel>

      <ActionDock>
        <template #primary>
          <Button
            class="dock-btn"
            variant="solid"
            theme="green"
            size="2xl"
            :disabled="create.loading || uploading || !form.subject"
            :loading="create.loading"
            :label="t('tickets.raise')"
            @click="submit"
          >
            <template #prefix><Icon name="help" :size="20" /></template>
          </Button>
        </template>
      </ActionDock>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { Button, FormControl, createResource } from "frappe-ui";
import ActionDock from "@shared/components/ActionDock.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import Panel from "@shared/components/Panel.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import Skeleton from "../components/Skeleton.vue";
import { useI18n, resourceErrorMessage, ISSUE_CATEGORIES, ISSUE_PRIORITIES } from "../i18n";
import { pushToast } from "../toast";
import { readPhotoFile, UnsupportedPhotoType } from "../upload";
import { PHOTO_ACCEPT } from "@shared/photoFile.js";
import { isCurrentTicketRequest, mergeCommunicationPages } from "../ticketPagination";

const { t, te } = useI18n();

const categories = ISSUE_CATEGORIES;
const priorities = ISSUE_PRIORITIES;
const categoryOptions = computed(() => categories.map((value) => ({ value, label: te("issueCategory", value) })));
const priorityOptions = computed(() => priorities.map((value) => ({ value, label: te("issuePriority", value) })));

const err = ref("");
const form = reactive({ category: "Vehicle", priority: "Medium", subject: "", description: "" });

const photo = ref({ photo: null, photo_filename: null });
const photoName = ref("");
const photoError = ref("");
const uploading = ref(false);
const photoInput = ref(null);

function choosePhoto() {
  photoInput.value?.click();
}

const list = createResource({
  url: "apex.salis.api.driver_portal.my_support_tickets",
  auto: true,
});
const listErrorMessage = computed(() => resourceErrorMessage(list.error, "errors.loadFailed"));
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

async function onPhoto(e) {
  const file = e.target.files && e.target.files[0];
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
const detailErrorMessage = computed(() =>
  resourceErrorMessage(detailError.value, "errors.loadFailed"),
);
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
  list.reload();
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

function statusTone(status) {
  const s = (status || "").toLowerCase();
  if (s === "resolved" || s === "closed") return "success";
  if (s === "waiting") return "warning";
  if (s === "cancelled") return "danger";
  return "accent";
}
</script>
