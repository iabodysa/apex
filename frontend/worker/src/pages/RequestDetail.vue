<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <HousingNav />
    <router-link to="/requests" class="back-link" style="text-decoration: none">
      <Icon name="chevron" :size="18" class="back-chevron" />
      <span>{{ t("requests.back") }}</span>
    </router-link>

    <div v-if="detail.loading" class="text-muted text-sm">{{ t("common.loading") }}</div>

    <div v-else-if="detail.error" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("errors.loadError") }}</p>
      <p class="text-sm text-muted">{{ errorMessage }}</p>
      <Button class="mt-3" variant="outline" size="xl" :label="t('common.retry')" @click="detail.reload()" />
    </div>

    <template v-else-if="data">
      <section class="card card-pad space-y-2">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-base font-extrabold leading-tight">
              {{ tEnum("requestCategory", data.request_category) }}
            </div>
            <div class="mt-0.5 text-xs text-muted">
              {{ t("requests.reference") }}: <bdi>{{ data.name }}</bdi>
            </div>
          </div>
          <span class="pill shrink-0" :class="statusPill(data.status)">{{ tEnum("requestStatus", data.status) }}</span>
        </div>
        <div v-if="data.priority || data.issue_location" class="text-xs text-muted">
          <span v-if="data.priority">{{ tEnum("priority", data.priority) }}</span>
          <span v-if="data.priority && data.issue_location"> · </span>
          <span v-if="data.issue_location">{{ tEnum("issueLocation", data.issue_location) }}</span>
        </div>
      </section>

      <section v-if="data.timeline && data.timeline.length" class="card card-pad space-y-3">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("requests.timeline") }}</h3>
        <ol class="timeline">
          <li v-for="(step, i) in data.timeline" :key="i" class="timeline-row">
            <span class="timeline-dot" :class="i === data.timeline.length - 1 ? 'timeline-dot-active' : ''">
              <Icon :name="i === data.timeline.length - 1 ? 'check' : 'clock'" :size="12" />
            </span>
            <div class="min-w-0 pb-1">
              <div class="font-semibold leading-tight">{{ timelineLabel(step) }}</div>
              <div class="text-xs text-muted">{{ tEnum("requestStatus", step.status) }}</div>
              <div v-if="step.timestamp" class="text-xs text-muted">
                <bdi>{{ formatDateTime(step.timestamp) }}</bdi>
              </div>
            </div>
          </li>
        </ol>
      </section>

      <section class="card card-pad space-y-4">
        <div v-if="data.description">
          <div class="field-label">{{ t("requests.details") }}</div>
          <p class="text-sm text-soft whitespace-pre-line">{{ data.description }}</p>
        </div>

        <div>
          <div class="field-label">{{ t("requests.triage") }}</div>
          <p class="text-sm" :class="data.triage_notes ? 'text-soft whitespace-pre-line' : 'text-muted'">
            {{ data.triage_notes || t("requests.noTriage") }}
          </p>
        </div>

        <div>
          <div class="field-label">{{ t("requests.resolution") }}</div>
          <p class="text-sm" :class="data.resolution_notes ? 'text-soft whitespace-pre-line' : 'text-muted'">
            {{ data.resolution_notes || t("requests.noResolution") }}
          </p>
        </div>
      </section>

      <section v-if="data.attachment" class="card card-pad space-y-2">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("requests.attachment") }}</h3>
        <a :href="data.attachment" target="_blank" rel="noopener" class="attach-tile" style="text-decoration: none">
          <img v-if="isImage(data.attachment)" :src="data.attachment" alt="" class="attach-thumb" />
          <span v-else class="attach-icon"><Icon name="doc" :size="22" /></span>
          <span class="min-w-0 flex-1">
            <span class="block font-semibold truncate"><bdi>{{ attachmentName }}</bdi></span>
            <span class="block text-xs text-muted">{{ t("requests.viewAttachment") }}</span>
          </span>
          <Icon name="external" :size="18" class="text-muted shrink-0" />
        </a>
      </section>
    </template>

    <div v-else-if="!detail.loading" class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("requests.notFound") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { Button, createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import HousingNav from "../components/HousingNav.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatDateTime } from "../utils/datetime";

const { t, tEnum } = useI18n();
const route = useRoute();

const detail = createResource({
  url: "apex.salis.api.masar.get_worker_request_detail",
  makeParams: () => ({ name: route.params.name }),
  auto: true,
});

const data = computed(() => detail.data || null);
const errorMessage = computed(() => resourceErrorMessage(detail.error));

const attachmentName = computed(() => {
  const url = data.value?.attachment || "";
  try {
    return decodeURIComponent(url.split("/").pop().split("?")[0]) || url;
  } catch (e) {
    return url;
  }
});

function isImage(url) {
  return /\.(png|jpe?g|gif|webp|svg|bmp|heic)(\?|$)/i.test(url || "");
}

function timelineLabel(step) {
  if (step.key === "created") return t("requests.timelineCreated");
  if (step.key === "closed") return t("requests.timelineClosed");
  return t("requests.timelineCurrent");
}

function statusPill(status) {
  const s = (status || "").toLowerCase();
  if (s === "resolved" || s === "closed") return "pill-success";
  if (s === "in progress" || s === "assigned" || s === "triaged") return "pill-warning";
  if (s === "rejected") return "pill-danger";
  return "pill-accent";
}
</script>

<style scoped>
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: var(--tap-min);
  padding-inline: 4px;
  margin-inline: -4px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--c-muted);
}
@media (hover: hover) {
  .back-link:hover {
    color: var(--c-ink);
  }
}
[dir="rtl"] .back-chevron {
  transform: scaleX(-1);
}

.timeline {
  display: flex;
  flex-direction: column;
}
.timeline-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  position: relative;
}
.timeline-row:not(:last-child) .timeline-dot::after {
  content: "";
  position: absolute;
  inset-block-start: 24px;
  inset-block-end: -8px;
  inline-size: 2px;
  background: color-mix(in srgb, var(--c-primary) 25%, transparent);
}
.timeline-dot {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  inline-size: 24px;
  block-size: 24px;
  flex-shrink: 0;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-primary) 12%, transparent);
  color: var(--c-primary);
}
.timeline-dot-active {
  background: var(--c-primary);
  color: var(--c-primary-ink);
}

.attach-tile {
  display: flex;
  align-items: center;
  gap: 12px;
}
.attach-thumb {
  inline-size: 48px;
  block-size: 48px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.attach-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  inline-size: 48px;
  block-size: 48px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-primary) 12%, transparent);
  color: var(--c-primary);
}
</style>
