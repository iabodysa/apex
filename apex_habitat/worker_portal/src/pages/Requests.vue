<!-- Copyright (c) 2026, AFMCO and contributors -->
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

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="field-label">{{ t("requests.issueLocation") }}</label>
          <!-- option VALUES stay English (sent to the API); only labels translate. -->
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

      <!-- Photo (optional): read client-side to a data-URL and POSTed as base64 on
           the same token-scoped create call; the server persists it as a private
           File on the new request. No separate guest upload surface. -->
      <div>
        <label class="field-label">{{ t("requests.photo") }}</label>
        <div class="photo-row">
          <label class="btn btn-outline photo-pick">
            <Icon name="image" :size="18" />
            {{ photo.dataUrl ? t("requests.photoChange") : t("requests.photoAdd") }}
            <input
              type="file"
              accept="image/*"
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
      <p v-if="ok" class="status-note status-ok">{{ t("requests.submitted") }}</p>
      <p v-if="err" class="status-note status-err">{{ err }}</p>
    </section>

    <!-- My requests -->
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

    <!-- Error loading the worker's request list: a revoked/disabled token
         (PermissionError) or server failure must surface, not read as "no
         requests yet". The new-request form above stays usable. -->
    <div v-else-if="list.error" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("errors.loadError") }}</p>
      <p class="text-sm text-muted">{{ listErrorMessage }}</p>
      <button class="btn btn-primary mt-3" style="width: auto; padding-inline: 24px" @click="list.reload()">
        {{ t("common.retry") }}
      </button>
    </div>

    <!-- List still loading: skeleton cards in place of the request rows. The
         new-request form above stays interactive throughout. -->
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
import { TOKEN } from "../utils/token";

const { t, tEnum } = useI18n();

const ok = ref(false);
const err = ref("");
const form = reactive({
  category: "Maintenance",
  priority: "Low",
  issue_location: "",
  preferred_language: "Arabic", // workers default to Arabic (see i18n detectInitial)
  subject: "",
  body: "",
});

// Selected photo, read client-side to a data-URL (base64). Sent on the same
// token-scoped create call; the server persists it as a private File. 8 MB cap
// mirrors the server WORKER_PHOTO_MAX_BYTES guard.
const PHOTO_MAX_BYTES = 8 * 1024 * 1024;
const photo = reactive({ dataUrl: "", name: "" });

const canSubmit = computed(() => !!(form.subject.trim() || form.body.trim()));

function clearPhoto() {
  photo.dataUrl = "";
  photo.name = "";
}

function onPhoto(e) {
  const file = e.target.files && e.target.files[0];
  // reset the input so re-picking the same file re-fires change
  e.target.value = "";
  if (!file) return;
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
  url: "apex_habitat.salis.api.masar.list_worker_requests",
  params: { token: TOKEN },
  auto: true,
});

const listErrorMessage = computed(() => resourceErrorMessage(list.error));

const create = createResource({
  url: "apex_habitat.salis.api.masar.create_worker_request",
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
    token: TOKEN,
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
/* The row chevron points toward the detail; flip it under RTL. No other
   direction-specific rules (T-297) — the rest is logical-property layout. */
[dir="rtl"] .row-chevron {
  transform: scaleX(-1);
}

/* Photo picker — logical-property layout only, so it mirrors under RTL with no
   direction-specific rule (T-297). The native file input is visually hidden but
   stays the click target inside its styled label. */
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
  background: none;
  border: 0;
  padding: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--c-danger, #dc2626);
  cursor: pointer;
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
  border-radius: var(--radius-sm, 8px);
  flex-shrink: 0;
}
</style>
