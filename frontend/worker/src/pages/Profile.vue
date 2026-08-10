<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <template v-if="p && p.employee">
      <section class="card card-pad">
        <div class="flex items-center gap-3">
          <span
            class="avatar h-14 w-14 text-xl overflow-hidden"
            style="background: var(--c-primary); color: var(--c-primary-ink)"
          >
            <img v-if="p.photo" :src="p.photo" alt="" class="h-full w-full object-cover" />
            <template v-else>{{ initial }}</template>
          </span>
          <div class="min-w-0">
            <div class="text-lg font-bold leading-tight truncate">
              {{ p.employee_name || t("common.none") }}
            </div>
            <StatusLabel
              class="mt-1"
              :label="p.status ? tEnum('status', p.status) : t('common.none')"
              :tone="statusTone"
            />
          </div>
        </div>

        <div class="divider my-4"></div>

        <dl class="space-y-3 text-sm">
          <Row icon="card" :label="t('profile.employeeNo')" :value="p.employee_number" />
          <Row v-if="p.designation" icon="briefcase" :label="t('profile.designation')" :value="p.designation" />
          <Row v-if="p.department" icon="layers" :label="t('profile.department')" :value="p.department" />
          <Row v-if="p.project" icon="briefcase" :label="t('profile.project')" :value="p.project" />
          <Row v-if="p.date_of_joining" icon="calendar" :label="t('profile.joined')" :value="formatDate(p.date_of_joining)" />
          <Row v-if="p.cell_number" icon="phone" :label="t('profile.phone')" :value="p.cell_number" />
        </dl>
      </section>

      <Panel v-if="p.documents && p.documents.length" :title="t('profile.documents')">
        <div v-for="doc in p.documents" :key="doc.type" class="card card-pad">
          <div class="flex items-center gap-2">
            <Icon name="doc" :size="18" class="text-primary shrink-0" />
            <span class="font-bold">{{ t("profile." + doc.type) }}</span>
            <StatusLabel
              v-if="docStatus(doc)"
              class="ms-auto"
              :label="docStatus(doc).text"
              :tone="docStatus(doc).tone"
            />
          </div>
          <dl class="mt-3 space-y-2 text-sm">
            <div v-if="doc.number" class="flex items-center gap-2">
              <dt class="text-muted">#</dt>
              <dd class="ms-auto font-semibold"><bdi>{{ doc.number }}</bdi></dd>
            </div>
            <div class="flex items-center gap-2" :class="docColor(doc)">
              <dt class="text-muted">{{ t("profile.expires") }}</dt>
              <dd class="ms-auto font-semibold">
                <bdi>{{ doc.expiry ? formatDate(doc.expiry) : t("profile.noExpiry") }}</bdi>
              </dd>
            </div>
          </dl>
        </div>
      </Panel>

      <Panel :title="t('lang.label')">
        <div class="flex items-center gap-2">
          <Icon name="globe" :size="18" class="text-primary shrink-0" />
          <div class="ms-auto"><LangToggle /></div>
        </div>
      </Panel>

      <ActionDock>
        <template #primary>
          <router-link to="/requests" class="btn btn-outline" style="text-decoration: none">
            <Icon name="plus" :size="18" /> {{ t("profile.requestChange") }}
          </router-link>
        </template>
      </ActionDock>
    </template>

    <EmptyState v-else :title="t('profile.empty')" :hint="t('profile.emptyHint')">
      <template #icon><Icon name="user" :size="22" /></template>
    </EmptyState>
  </div>
</template>

<script setup>
import { computed, h } from "vue";
import ActionDock from "@shared/components/ActionDock.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import Panel from "@shared/components/Panel.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import Icon from "../components/Icon.vue";
import LangToggle from "../components/LangToggle.vue";
import { useI18n } from "../i18n";
import { formatDate } from "../utils/datetime";

const { t, tEnum } = useI18n();

const props = defineProps({ ctx: { type: Object, required: true } });
const p = computed(() => props.ctx);

const Row = (rprops) =>
  h("div", { class: "flex items-center gap-2" }, [
    h(Icon, { name: rprops.icon, size: 18, class: "text-primary shrink-0" }),
    h("dt", { class: "text-muted" }, rprops.label),
    h("dd", { class: "ms-auto font-semibold" }, h("bdi", null, rprops.value || t("common.none"))),
  ]);

const initial = computed(
  () => (props.ctx.employee_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const statusTone = computed(() => {
  const s = (props.ctx.status || "").toLowerCase();
  if (s === "active") return "success";
  if (s === "left" || s === "suspended" || s === "inactive") return "danger";
  return "neutral";
});

function docColor(doc) {
  const d = doc.days_left;
  if (d == null) return "";
  if (d < 0) return "text-danger";
  if (d <= 30) return "text-warning";
  return "";
}
function docStatus(doc) {
  const d = doc.days_left;
  if (d == null) return null;
  if (d < 0) return { tone: "danger", text: t("profile.expired") };
  if (d <= 30) return { tone: "warning", text: t("profile.daysLeft", { n: d }) };
  return null;
}
</script>
