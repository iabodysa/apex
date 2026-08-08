<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <MobileConsoleShell :max-width="560">
    <template #header>
      <div class="head-row">
        <div class="head-id">
          <small class="head-sub">{{ screenName }}</small>
          <b class="head-title">{{ headTitle }}</b>
        </div>
        <div class="head-actions">
          <LangToggle variant="header" />
          <Button
            v-if="usesBuilding && building"
            size="xl"
            variant="ghost"
            class="head-btn"
            :label="t('common.changeBuilding')"
            :tooltip="t('common.changeBuilding')"
            @click="onChangeBuilding"
          >
            <template #icon><Icon name="building" :size="24" /></template>
          </Button>
        </div>
      </div>
    </template>

    <template v-if="showProgress" #progress>
      <Progress
        class="head-progress"
        size="md"
        :value="progressPercent"
        :label="t('list.progressLabel')"
      >
        <template #hint>
          <span class="head-progress-hint">
            {{ t("list.progress", { done: countProgress.done, total: countProgress.total }) }}
          </span>
        </template>
      </Progress>
    </template>

    <router-view />

    <template v-if="tabs.length > 1" #nav>
      <router-link
        v-for="tab in tabs"
        :key="tab.path"
        class="nav-tab"
        :to="tab.path"
        :class="{ 'is-active': isActive(tab) }"
        :aria-current="isActive(tab) ? 'page' : undefined"
        active-class=""
        exact-active-class=""
      >
        <Icon :name="tab.icon" :size="24" />
        <span>{{ t(tab.labelKey) }}</span>
      </router-link>
    </template>
  </MobileConsoleShell>

  <Toast />
  <Dialogs />
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button, Dialogs, Progress, Toast } from "frappe-ui";
import MobileConsoleShell from "@shared/components/MobileConsoleShell.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import Icon from "./components/Icon.vue";
import { useI18n } from "./i18n";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { allowedSections, landingPath } from "./sections.js";
import { building, buildingLabel, clearBuilding, countProgress } from "./session";

const { t, lang, dir } = useI18n();
const route = useRoute();
const router = useRouter();

const BUILDING_SECTIONS = new Set(["count", "beds", "arrivals", "custody", "transfer", "safety"]);

const tabs = allowedSections();

function isActive(tab) {
  return route.path === tab.path || route.path.startsWith(tab.path + "/");
}

const currentSection = computed(() => (route.meta && route.meta.section) || "");
const usesBuilding = computed(() => BUILDING_SECTIONS.has(currentSection.value));
const onCount = computed(() => currentSection.value === "count");

const screenName = computed(() => {
  const tab = tabs.find((entry) => entry.id === currentSection.value);
  return tab ? t(tab.labelKey) : t("common.appName");
});
const headTitle = computed(() =>
  usesBuilding.value && buildingLabel.value ? buildingLabel.value : t("common.appName"),
);

const showProgress = computed(
  () => onCount.value && !!building.value && countProgress.value.total > 0,
);
const progressPercent = computed(() => {
  const { done, total } = countProgress.value;
  return total ? Math.round((done / total) * 100) : 0;
});

function onChangeBuilding() {
  clearBuilding();
  if (!currentSection.value) router.push(landingPath());
}

useDocumentLanguage(lang, dir);
</script>

<style scoped>
.head-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.head-id {
  min-width: 0;
}
.head-sub {
  display: block;
  font-size: var(--fs-sm);
  opacity: 0.72;
}
.head-title {
  display: block;
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.head-actions {
  margin-inline-start: auto;
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  flex-shrink: 0;
}

.head-actions :deep(.head-btn) {
  min-height: var(--tap-min);
  min-width: var(--tap-min);
  color: var(--c-header-ink);
  background: color-mix(in srgb, var(--c-header-ink) 14%, transparent);
}
@media (hover: hover) {
  .head-actions :deep(.head-btn:hover) {
    background: color-mix(in srgb, var(--c-header-ink) 24%, transparent);
  }
}

.head-progress :deep(span) {
  color: var(--c-header-ink);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
}
.head-progress-hint {
  opacity: 0.8;
}
.head-progress :deep([role="progressbar"]) {
  background: color-mix(in srgb, var(--c-header-ink) 22%, transparent);
}
.head-progress :deep([role="progressbar"] > div) {
  background: var(--c-header-accent);
}
</style>
