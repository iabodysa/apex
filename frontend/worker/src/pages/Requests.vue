<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("requests.title") }}</h2>

    <section class="card card-pad space-y-3">
      <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("requests.new") }}</h3>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="field-label">{{ t("requests.category") }}</label>
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

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="field-label">{{ t("requests.issueLocation") }}</label>
          <select v-model="form.issue_location" class="select">
            <option value="">{{ t("requests.issueLocationNone") }}</option>
            <option value="Room">{{ t("requests.locRoom") }}</option>
            <option value="Bathroom">{{ t("requests.locBathroom") }}</option>
            <option value="Kitchen">{{ t("requests.locKitchen") }}</option>
            <option value="Common Area">{{ t("requests.locCommonArea") }}</option>
            <option value="Entrance">{{ t("requests.locEntrance") }}</option>
            <option value="Staircase">{{ t("requests.locStaircase") }}</option>
            <option value="External Area">{{ t("requests.locExternalArea") }}</option>
            <option value="Other">{{ t("requests.locOther") }}</option>
          </select>
        </div>
        <div>
          <label class="field-label">{{ t("requests.prefLang") }}</label>
          <select v-model="form.preferred_language" class="select">
            <option value="Arabic">{{ t("requests.langArabic") }}</option>
            <option value="English">{{ t("requests.langEnglish") }}</option>
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

      <div>
        <label class="field-label">{{ t("requests.photo") }}</label>
        <div class="photo-row">
          <label class="btn btn-outline photo-pick">
            <Icon name="image" :size="18" />
            {{ photo.dataUrl ? t("requests.photoChange") : t("requests.photoAdd") }}
            <input
              type="file"
              :accept="PHOTO_ACCEPT"
              class="photo-input"
              @change="onPhoto"
            />
          </label>
          <button v-if="photo.dataUrl" type="button" class="photo-remove" @click="clearPhoto">
            {{ t("requests.photoRemove") }}
          </button>
        </div>
        <div v-if="photo.dataUrl" class="photo-preview">
          <img :src="photo.dataUrl" alt="" />
          <span class="truncate text-xs text-muted"><bdi>{{ photo.name }}</bdi></span>
        </div>
      </div>

      <button class="btn btn-primary" :disabled="create.loading || !canSubmit" @click="submit">
        <Icon name="send" :size="20" /> {{ t("requests.submit") }}
      </button>
      <p v-if="!canSubmit" class="text-xs text-muted">{{ t("requests.needText") }}</p>
      <p v-if="ok" class="status-note status-ok">{{ t("requests.submitted") }}</p>
      <p v-if="err" class="status-note status-err">{{ err }}</p>
    </section>

    <section v-if="list.data && list.data.length" class="space-y-3">
      <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("requests.mine") }}</h3>
      <router-link
        v-for="r in list.data"
        :key="r.name"
        :to="`/requests/${encodeURIComponent(r.name)}`"
        class="card card-pad block"
        style="text-decoration: none"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="font-bold leading-tight">{{ tEnum("requestCategory", r.request_category) }}</div>
          <span class="pill shrink-0" :class="statusPill(r.status)">{{ tEnum("requestStatus", r.status) }}</span>
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
    </section>

    <div v-else-if="list.error" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("errors.loadError") }}</p>
      <p class="text-sm text-muted">{{ listErrorMessage }}</p>
      <button class="btn btn-primary mt-3" style="width: auto; padding-inline: 24px" @click="list.reload()">
        {{ t("common.retry") }}
      </button>
    </div>

    <section v-else-if="list.loading" class="space-y-3">
      <Skeleton :lines="2" />
      <Skeleton :lines="2" />
    </section>

    <div v-else class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("requests.empty") }}</p>
      <p class="text-xs text-muted mt-1">{{ t("requests.emptyHint") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
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
  width: auto;
  padding-inline: 16px;
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
.photo-remove {
  display: inline-flex;
  align-items: center;
  min-height: var(--tap-min);
  background: none;
  border: 0;
  padding-block: 0;
  padding-inline: 4px;
  margin-inline: -4px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--c-danger);
  cursor: pointer;
}
@media (hover: hover) {
  .photo-remove:hover {
    text-decoration: underline;
  }
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
