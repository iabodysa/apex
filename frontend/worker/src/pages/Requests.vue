<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <HousingNav />
    <Panel :title="t('requests.new')">
      <div class="space-y-3">
      <div class="form-pair">
        <FormControl v-model="form.category" type="select" size="lg" :label="t('requests.category')" :options="categoryOptions" />
        <FormControl v-model="form.priority" type="select" size="lg" :label="t('requests.priority')" :options="priorityOptions" />
      </div>

      <div class="form-pair">
        <FormControl v-model="form.issue_location" type="select" size="lg" :label="t('requests.issueLocation')" :options="locationOptions" />
        <FormControl v-model="form.preferred_language" type="select" size="lg" :label="t('requests.prefLang')" :options="languageOptions" />
      </div>

      <FormControl v-model="form.subject" type="text" size="lg" :label="t('requests.subject')" :placeholder="t('requests.subjectPlaceholder')" />
      <FormControl v-model="form.body" type="textarea" size="lg" :rows="4" :label="t('requests.description')" :placeholder="t('requests.descriptionPlaceholder')" />

      <div>
        <label class="field-label">{{ t("requests.photo") }}</label>
        <div class="photo-row">
          <label class="photo-pick">
            <Icon name="image" :size="18" />
            {{ photo.dataUrl ? t("requests.photoChange") : t("requests.photoAdd") }}
            <input
              type="file"
              :accept="PHOTO_ACCEPT"
              class="photo-input"
              @change="onPhoto"
            />
          </label>
          <Button v-if="photo.dataUrl" type="button" variant="ghost" theme="red" size="lg" :label="t('requests.photoRemove')" @click="clearPhoto" />
        </div>
        <div v-if="photo.dataUrl" class="photo-preview">
          <img :src="photo.dataUrl" alt="" />
          <span class="truncate text-xs text-muted"><bdi>{{ photo.name }}</bdi></span>
        </div>
      </div>

      <p v-if="ok" class="status-note status-ok">{{ t("requests.submitted") }}</p>
      <p v-if="err" class="status-note status-err">{{ err }}</p>
      </div>
    </Panel>

    <Panel :title="t('requests.mine')">
      <template v-if="list.data && list.data.length">
        <router-link
          v-for="r in list.data"
          :key="r.name"
          :to="`/requests/${encodeURIComponent(r.name)}`"
          class="card card-pad block"
          style="text-decoration: none"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="font-bold leading-tight">{{ tEnum("requestCategory", r.request_category) }}</div>
            <StatusLabel class="shrink-0" :label="tEnum('requestStatus', r.status)" :tone="statusTone(r.status)" />
          </div>
          <p class="mt-1 text-sm text-soft whitespace-pre-line line-clamp-3">{{ r.description }}</p>
          <div class="mt-1 flex items-center justify-between gap-2">
            <div class="text-xs text-muted">{{ tEnum("priority", r.priority) }} · <bdi>{{ formatDate(r.creation) }}</bdi></div>
            <Icon name="chevron" :size="16" class="text-muted shrink-0 row-chevron" />
          </div>
          <div v-if="r.resolution_notes" class="mt-2 text-sm">
            <span class="text-muted">{{ t("requests.resolution") }}:</span>
            <span class="font-semibold"> {{ r.resolution_notes }}</span>
          </div>
        </router-link>
      </template>

      <LoadError
        v-else-if="list.error"
        :title="t('errors.loadError')"
        :detail="listErrorMessage"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="list.reload()"
      />

      <div v-else-if="list.loading" class="space-y-3">
        <Skeleton :lines="2" />
        <Skeleton :lines="2" />
      </div>

      <EmptyState v-else :title="t('requests.empty')" :hint="t('requests.emptyHint')">
        <template #icon><Icon name="plus" :size="22" /></template>
      </EmptyState>
    </Panel>

    <ActionDock>
      <template #secondary>
        <p v-if="!canSubmit" class="row-reason">{{ t("requests.needText") }}</p>
      </template>
      <template #primary>
        <Button
          class="dock-btn"
          variant="solid"
          theme="green"
          size="2xl"
          :disabled="create.loading || !canSubmit"
          :loading="create.loading"
          :label="t('requests.submit')"
          @click="submit"
        >
          <template #prefix><Icon name="send" :size="20" /></template>
        </Button>
      </template>
    </ActionDock>
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
import HousingNav from "../components/HousingNav.vue";
import Skeleton from "../components/Skeleton.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { PHOTO_ACCEPT, isAcceptedPhoto } from "@shared/photoFile.js";

const { t, tEnum } = useI18n();

const ok = ref(false);
const err = ref("");
const form = reactive({
  category: "Maintenance",
  priority: "Low",
  issue_location: "",
  preferred_language: "Arabic",
  subject: "",
  body: "",
});

const PHOTO_MAX_BYTES = 8 * 1024 * 1024;
const photo = reactive({ dataUrl: "", name: "" });

const canSubmit = computed(() => !!(form.subject.trim() || form.body.trim()));

const categoryOptions = computed(() => [
  ["Maintenance", "catMaintenance"], ["Cleaning", "catCleaning"], ["AC", "catAC"],
  ["Plumbing", "catPlumbing"], ["Electrical", "catElectrical"], ["Water", "catWater"],
  ["Pest Control", "catPestControl"], ["Custody", "catCustody"], ["Complaint", "catComplaint"],
  ["Suggestion", "catSuggestion"], ["Other", "catOther"],
].map(([value, key]) => ({ value, label: t(`requests.${key}`) })));
const priorityOptions = computed(() => ["Low", "Medium", "High", "Critical"].map((value) => ({
  value,
  label: t(`requests.prio${value}`),
})));
const locationOptions = computed(() => [
  ["", "issueLocationNone"], ["Room", "locRoom"], ["Bathroom", "locBathroom"],
  ["Kitchen", "locKitchen"], ["Common Area", "locCommonArea"], ["Entrance", "locEntrance"],
  ["Staircase", "locStaircase"], ["External Area", "locExternalArea"], ["Other", "locOther"],
].map(([value, key]) => ({ value, label: t(`requests.${key}`) })));
const languageOptions = computed(() => [
  { value: "Arabic", label: t("requests.langArabic") },
  { value: "English", label: t("requests.langEnglish") },
]);

function clearPhoto() {
  photo.dataUrl = "";
  photo.name = "";
}

function onPhoto(e) {
  const file = e.target.files && e.target.files[0];
  e.target.value = "";
  if (!file) return;
  if (!isAcceptedPhoto(file)) {
    clearPhoto();
    err.value = t("requests.photoType");
    return;
  }
  if (file.size > PHOTO_MAX_BYTES) {
    clearPhoto();
    err.value = t("requests.photoTooLarge");
    return;
  }
  err.value = "";
  const reader = new FileReader();
  reader.onload = () => {
    photo.dataUrl = String(reader.result || "");
    photo.name = file.name || "photo.jpg";
  };
  reader.readAsDataURL(file);
}

const list = createResource({
  url: "apex.salis.api.masar.list_worker_requests",
  auto: true,
});

const listErrorMessage = computed(() => resourceErrorMessage(list.error));

const create = createResource({
  url: "apex.salis.api.masar.create_worker_request",
  onSuccess: () => {
    form.subject = "";
    form.body = "";
    form.issue_location = "";
    clearPhoto();
    err.value = "";
    ok.value = true;
    setTimeout(() => (ok.value = false), 3000);
    list.reload();
  },
  onError: (e) => {
    ok.value = false;
    err.value = resourceErrorMessage(e, "common.error");
  },
});

function submit() {
  ok.value = false;
  err.value = "";
  create.submit({
    category: form.category,
    priority: form.priority,
    issue_location: form.issue_location,
    preferred_language: form.preferred_language,
    subject: form.subject,
    body: form.body,
    photo: photo.dataUrl || undefined,
    photo_filename: photo.dataUrl ? photo.name : undefined,
  });
}

function statusTone(status) {
  const s = (status || "").toLowerCase();
  if (s === "resolved" || s === "closed") return "success";
  if (s === "in progress" || s === "assigned" || s === "triaged") return "warning";
  if (s === "rejected") return "danger";
  return "accent";
}

function formatDate(c) {
  return (c || "").slice(0, 10);
}
</script>

<style scoped>
[dir="rtl"] .row-chevron {
  transform: scaleX(-1);
}

.photo-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.photo-pick {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-block-size: var(--tap-min);
  padding: var(--sp-2) var(--sp-4);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius-sm);
  color: var(--c-ink);
  font-weight: var(--fw-semibold);
  cursor: pointer;
}
.photo-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.photo-preview {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-block-start: 10px;
}
.photo-preview img {
  inline-size: 56px;
  block-size: 56px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
</style>
