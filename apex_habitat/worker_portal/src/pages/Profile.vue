<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("profile.title") }}</h2>

    <template v-if="p && p.employee">
      <!-- Identity card -->
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
            <div class="text-lg font-extrabold leading-tight truncate">
              {{ p.employee_name || t("common.none") }}
            </div>
            <span class="pill mt-1" :class="statusPill">{{ p.status ? tEnum("status", p.status) : t("common.none") }}</span>
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

      <!-- Documents with expiry warnings -->
      <section v-if="p.documents && p.documents.length" class="space-y-3">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("profile.documents") }}</h3>
        <div v-for="doc in p.documents" :key="doc.type" class="card card-pad">
          <div class="flex items-center gap-2">
            <Icon name="doc" :size="18" class="text-primary shrink-0" />
            <span class="font-bold">{{ t("profile." + doc.type) }}</span>
            <span v-if="docPill(doc)" class="pill ms-auto" :class="docPill(doc).cls">{{ docPill(doc).text }}</span>
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
      </section>

      <!-- Secondary sections moved out of the bottom bar: reachable from here. -->
      <section class="space-y-3">
        <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("profile.more") }}</h3>
        <div class="card">
          <router-link
            v-for="(link, i) in moreLinks"
            :key="link.to"
            :to="link.to"
            class="flex items-center gap-3 card-pad"
            :class="{ 'border-t': i > 0 }"
            style="text-decoration: none; border-color: var(--c-border)"
          >
            <Icon :name="link.icon" :size="18" class="text-primary shrink-0" />
            <span class="font-semibold">{{ t(link.labelKey) }}</span>
            <Icon name="chevron" :size="18" class="ms-auto text-muted shrink-0 rtl-flip" />
          </router-link>
        </div>
      </section>

      <!-- Request a data change → opens the Requests tab. -->
      <router-link to="/requests" class="btn btn-outline" style="text-decoration: none">
        <Icon name="plus" :size="18" /> {{ t("profile.requestChange") }}
      </router-link>

      <section class="card card-pad">
        <div class="flex items-center gap-2">
          <Icon name="globe" :size="18" class="text-primary shrink-0" />
          <span class="text-sm font-semibold">{{ t("lang.label") }}</span>
          <div class="ms-auto"><LangToggle /></div>
        </div>
      </section>
    </template>

    <div v-else class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("profile.empty") }}</p>
      <p class="text-xs text-muted mt-1">{{ t("profile.emptyHint") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, h } from "vue";
import Icon from "../components/Icon.vue";
import LangToggle from "../components/LangToggle.vue";
import { useI18n } from "../i18n";
import { formatDate } from "../datetime";

const { t, tEnum } = useI18n();

const props = defineProps({ ctx: { type: Object, required: true } });
const p = computed(() => props.ctx);

// Secondary destinations lifted out of the bottom bar; same nav labels/icons.
const moreLinks = [
  { to: "/accommodation", icon: "building", labelKey: "nav.accommodation" },
  { to: "/custody", icon: "briefcase", labelKey: "nav.custody" },
  { to: "/requests", icon: "message", labelKey: "nav.requests" },
];

// Tiny inline label/value row to keep the template tidy.
const Row = (rprops) =>
  h("div", { class: "flex items-center gap-2" }, [
    h(Icon, { name: rprops.icon, size: 18, class: "text-primary shrink-0" }),
    h("dt", { class: "text-muted" }, rprops.label),
    // <bdi> isolates Latin/numeric values (employee no., joined date, phone)
    // inside the RTL row; a no-op for Arabic/text values. [T-313]
    h("dd", { class: "ms-auto font-semibold" }, h("bdi", null, rprops.value || t("common.none"))),
  ]);

const initial = computed(
  () => (props.ctx.employee_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const statusPill = computed(() => {
  const s = (props.ctx.status || "").toLowerCase();
  if (s === "active") return "pill-success";
  if (s === "left" || s === "suspended" || s === "inactive") return "pill-danger";
  return "pill-neutral";
});

function docColor(doc) {
  const d = doc.days_left;
  if (d == null) return "";
  if (d < 0) return "text-danger";
  if (d <= 30) return "text-warning";
  return "";
}
function docPill(doc) {
  const d = doc.days_left;
  if (d == null) return null;
  if (d < 0) return { cls: "pill-danger", text: t("profile.expired") };
  if (d <= 30) return { cls: "pill-warning", text: t("profile.daysLeft", { n: d }) };
  return null;
}
</script>
