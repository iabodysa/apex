<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <HousingNav />
    <router-link to="/requests" class="back-link" style="text-decoration: none">
      <Icon name="chevron" :size="18" class="back-chevron" />
      <span>{{ t("requests.back") }}</span>
    </router-link>

    <Skeleton v-if="detail.loading" :lines="4" />

    <LoadError
      v-else-if="detail.error"
      :title="t('errors.loadError')"
      :detail="errorMessage"
      :hint="t('errors.retryHint')"
      :retry-label="t('common.retry')"
      @retry="detail.reload()"
    />

    <template v-else-if="data">
      <section class="card card-pad space-y-2">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-base font-bold leading-tight">
              {{ tEnum("requestCategory", data.request_category) }}
            </div>
            <div class="mt-0.5 text-xs text-muted">
              {{ t("requests.reference") }}: <bdi>{{ data.name }}</bdi>
            </div>
          </div>
          <StatusLabel class="shrink-0" :label="tEnum('requestStatus', data.status)" :tone="statusTone(data.status)" />
        </div>
        <div v-if="data.priority || data.issue_location" class="text-xs text-muted">
          <span v-if="data.priority">{{ tEnum("priority", data.priority) }}</span>
          <span v-if="data.priority && data.issue_location"> · </span>
          <span v-if="data.issue_location">{{ tEnum("issueLocation", data.issue_location) }}</span>
        </div>
      </section>

      <Panel v-if="data.timeline && data.timeline.length" :title="t('requests.timeline')">
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
      </Panel>

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

      <Panel v-if="data.attachment" :title="t('requests.attachment')">
        <a :href="data.attachment" target="_blank" rel="noopener" class="attach-tile" style="text-decoration: none">
          <img v-if="isImage(data.attachment)" :src="data.attachment" alt="" class="attach-thumb" />
          <span v-else class="attach-icon"><Icon name="doc" :size="22" /></span>
          <span class="min-w-0 flex-1">
            <span class="block font-semibold truncate"><bdi>{{ attachmentName }}</bdi></span>
            <span class="block text-xs text-muted">{{ t("requests.viewAttachment") }}</span>
          </span>
          <Icon name="external" :size="18" class="text-muted shrink-0" />
        </a>
      </Panel>
    </template>

    <EmptyState v-else-if="!detail.loading" :title="t('requests.notFound')">
      <template #icon><Icon name="doc" :size="22" /></template>
    </EmptyState>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { createResource } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import Panel from "@shared/components/Panel.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
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

function statusTone(status) {
  const s = (status || "").toLowerCase();
  if (s === "resolved" || s === "closed") return "success";
  if (s === "in progress" || s === "assigned" || s === "triaged") return "warning";
  if (s === "rejected") return "danger";
  return "accent";
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
  font-weight: 700;
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
