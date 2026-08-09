<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <PortalFrame
    :title="sceneTitle"
    :eyebrow="sceneEyebrow"
    :subtitle="sceneSubtitle"
    :navigation-label="t('nav.label')"
    :skip-label="t('common.skip')"
  >
    <template #brand>
      <Brand variant="reverse" :size="32" />
      <span class="brand-copy">
        <strong>{{ t("common.portalName") }}</strong>
        <small>{{ t("common.appName") }}</small>
      </span>
    </template>

    <template #header-actions>
      <Button
        v-if="usesBuilding && building"
        size="xl"
        variant="ghost"
        class="building-control"
        :label="buildingLabel || building"
        :tooltip="t('common.changeBuilding')"
        @click="clearBuilding"
      >
        <template #icon><Icon name="building" :size="20" /></template>
      </Button>
      <LangToggle variant="header" />
    </template>

    <section v-if="needsBuilding" class="building-stage" :aria-label="t('building.title')">
      <p class="stage-kicker">{{ t("building.context") }}</p>
      <BuildingSwitcher @select="selectBuilding" />
    </section>

    <template v-else>
      <div v-if="showProgress" class="scene-progress">
        <Progress
          size="md"
          :value="progressPercent"
          :label="t('list.progressLabel')"
        >
          <template #hint>
            <span>{{ t("list.progress", { done: countProgress.done, total: countProgress.total }) }}</span>
          </template>
        </Progress>
      </div>

      <nav v-if="subsections.length > 1" class="context-nav" :aria-label="t('nav.sectionLabel')">
        <TabButtons v-model="activeSubsection" :dir="dir" :buttons="subsectionButtons" />
      </nav>

      <router-view />
    </template>

    <template v-if="domains.length" #nav>
      <router-link
        v-for="domain in domains"
        :key="domain.id"
        :to="domain.path"
        :class="{ 'is-active': domainActive(domain) }"
        :aria-current="domainActive(domain) ? 'page' : undefined"
      >
        <Icon :name="domain.icon" :size="22" />
        <span>{{ t(domain.labelKey) }}</span>
      </router-link>
    </template>
  </PortalFrame>

  <Toast />
  <Dialogs />
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button, Dialogs, Progress, TabButtons, Toast } from "frappe-ui";
import Brand from "@shared/components/Brand.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import PortalFrame from "@shared/components/PortalFrame.vue";
import BuildingSwitcher from "./components/BuildingSwitcher.vue";
import Icon from "./components/Icon.vue";
import { useI18n } from "./i18n";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import {
  SECTIONS,
  allowedDomains,
  domainForSection,
  sectionsForDomain,
} from "./sections.js";
import { building, buildingLabel, clearBuilding, countProgress, selectBuilding } from "./session";

const { t, lang, dir } = useI18n();
const route = useRoute();
const router = useRouter();

const BUILDING_SECTIONS = new Set(["today", "count", "beds", "arrivals", "custody", "transfer", "safety"]);
const domains = allowedDomains();

const currentSection = computed(() => (route.meta && route.meta.section) || "");
const currentDomain = computed(
  () => (route.meta && route.meta.domain) || domainForSection(currentSection.value),
);
const usesBuilding = computed(() => BUILDING_SECTIONS.has(currentSection.value));
const needsBuilding = computed(() => usesBuilding.value && !building.value);

const sceneTitle = computed(() => {
  if (currentSection.value === "today") return t("today.title");
  const section = SECTIONS.find((entry) => entry.id === currentSection.value);
  return section ? t(section.labelKey) : t("common.appName");
});
const sceneEyebrow = computed(() =>
  usesBuilding.value && buildingLabel.value ? buildingLabel.value : t("common.operationalPortal"),
);
const sceneSubtitle = computed(() =>
  currentSection.value ? t(`scene.${currentSection.value}`) : "",
);

const subsections = computed(() => sectionsForDomain(currentDomain.value));
const subsectionButtons = computed(() =>
  subsections.value.map((section) => ({ label: t(section.labelKey), value: section.id })),
);
const activeSubsection = computed({
  get: () => currentSection.value,
  set: (id) => {
    const section = subsections.value.find((entry) => entry.id === id);
    if (section) router.push(section.path);
  },
});

function domainActive(domain) {
  return currentDomain.value === domain.id;
}

const showProgress = computed(
  () => currentSection.value === "count" && !!building.value && countProgress.value.total > 0,
);
const progressPercent = computed(() => {
  const { done, total } = countProgress.value;
  return total ? Math.round((done / total) * 100) : 0;
});

useDocumentLanguage(lang, dir);
</script>

<style scoped>
.brand-copy {
  display: grid;
  min-inline-size: 0;
  line-height: 1.15;
}
.brand-copy strong {
  color: var(--c-header-ink);
  font-family: var(--font-brand);
  font-size: var(--fs-sm);
  font-weight: var(--fw-heading);
}
.brand-copy small {
  color: color-mix(in srgb, var(--c-header-ink) 68%, transparent);
  font-family: var(--font-serif);
  font-size: var(--fs-xs);
}
.building-control {
  min-block-size: var(--tap-min);
  max-inline-size: min(38vw, 17rem);
  color: var(--c-header-ink);
  background: color-mix(in srgb, var(--c-header-ink) 10%, transparent);
}
.building-control :deep(span) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.building-stage {
  max-inline-size: 54rem;
  margin-inline: auto;
  padding-block: clamp(var(--sp-3), 3vw, var(--sp-8));
}
.stage-kicker {
  margin: 0 0 var(--sp-4);
  padding-block-end: var(--sp-3);
  border-block-end: 1px solid var(--c-border-strong);
  color: var(--c-accent-ink);
  font-family: var(--font-brand);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
}
.context-nav {
  margin-block-end: clamp(var(--sp-5), 3vw, var(--sp-8));
  padding-block-end: var(--sp-4);
  border-block-end: 1px solid var(--c-border-strong);
}
.context-nav :deep(button) {
  min-block-size: var(--tap-min);
}
.scene-progress {
  margin-block-end: var(--sp-4);
  padding-block-end: var(--sp-4);
  border-block-end: 1px solid var(--c-border-strong);
}
.scene-progress :deep([role="progressbar"] > div) {
  background: var(--c-primary);
}

@media (max-width: 32rem) {
  .brand-copy small,
  .building-control :deep(span:not(:first-child)) {
    display: none;
  }
  .building-control {
    inline-size: var(--tap-min);
    padding-inline: 0;
  }
}
</style>
