<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <FrappeUIProvider>
    <a class="console-skip" href="#portal-main">{{ t("common.skip") }}</a>

    <MobileConsoleShell>
    <template #header>
      <div class="console-head-row">
        <div class="console-identity">
          <span class="brand-mark"><Brand variant="reverse" :size="44" /></span>
          <span class="brand-copy">
            <strong>{{ portalName }}</strong>
            <small>{{ t("common.appName") }}</small>
          </span>
        </div>

        <div class="console-actions">
          <Button
            v-if="usesBuilding && building"
            size="xl"
            variant="ghost"
            class="building-control"
            :label="buildingLabel || building"
            :tooltip="t('common.changeBuilding')"
            @click="clearBuilding"
          >
            <template #prefix><Icon name="building" :size="20" /></template>
            <bdi dir="auto">{{ buildingLabel || building }}</bdi>
          </Button>
          <LangToggle variant="header" />
        </div>
      </div>
    </template>

    <template v-if="showContextList" #list>
      <section
        class="desktop-context"
        :class="{ 'is-narrow': narrowContextList }"
        :aria-label="t('nav.sectionLabel')"
      >
        <span class="scene-disc" aria-hidden="true">
          <Icon :name="sceneIcon" :size="24" />
        </span>
        <p class="context-kicker">
          <bdi v-if="showsBuilding && buildingLabel" dir="auto">{{ buildingLabel }}</bdi>
          <span v-else>{{ sceneEyebrow }}</span>
        </p>
        <h1>{{ sceneTitle }}</h1>
        <p v-if="sceneSubtitle" class="context-copy">{{ sceneSubtitle }}</p>

        <button
          v-if="showsBuilding && building"
          type="button"
          class="context-building"
          :aria-label="t('common.changeBuilding')"
          @click="clearBuilding"
        >
          <span class="context-building-icon"><Icon name="building" :size="20" /></span>
          <span>
            <small>{{ t("building.context") }}</small>
            <b><bdi dir="auto">{{ buildingLabel || building }}</bdi></b>
          </span>
          <span class="context-building-swap">{{ t("common.change") }}</span>
        </button>

        <nav
          v-if="subsections.length > 1"
          class="desktop-subnav"
          :aria-label="t('nav.sectionLabel')"
        >
          <router-link
            v-for="section in subsections"
            :key="section.id"
            :to="section.path"
            :class="{ 'is-active': currentSection === section.id }"
            :aria-current="currentSection === section.id ? 'page' : undefined"
          >
            <Icon :name="section.icon" :size="20" />
            <span>{{ t(section.labelKey) }}</span>
          </router-link>
        </nav>
      </section>
    </template>

    <section
      id="portal-main"
      class="console-scene"
      :class="{ 'has-context-list': showContextList }"
      tabindex="-1"
    >
      <section v-if="needsBuilding" class="building-stage">
        <Brand class="stage-lockup" :variant="lockupVariant" :alt="t('common.appName')" />
        <p class="stage-kicker">{{ t("building.context") }}</p>
        <h1 class="stage-title">{{ t("building.title") }}</h1>
        <BuildingSwitcher @select="selectBuilding" />
      </section>

      <template v-else>
        <header class="scene-heading">
          <span class="scene-disc" aria-hidden="true">
            <Icon :name="sceneIcon" :size="24" />
          </span>
          <div class="scene-copy">
            <p class="scene-eyebrow">
              <bdi v-if="showsBuilding && buildingLabel" dir="auto">{{ buildingLabel }}</bdi>
              <span v-else>{{ sceneEyebrow }}</span>
            </p>
            <h1>{{ sceneTitle }}</h1>
            <p v-if="sceneSubtitle" class="scene-subtitle">{{ sceneSubtitle }}</p>
          </div>
        </header>

        <nav
          v-if="subsections.length > 1"
          class="context-nav"
          :aria-label="t('nav.sectionLabel')"
        >
          <TabButtons v-model="activeSubsection" :dir="dir" :buttons="subsectionButtons" />
        </nav>

        <router-view />
      </template>
    </section>

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

    </MobileConsoleShell>
  </FrappeUIProvider>
</template>

<script setup>
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button, FrappeUIProvider, TabButtons, createResource } from "frappe-ui";
import Brand from "@shared/components/Brand.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import MobileConsoleShell from "@shared/components/MobileConsoleShell.vue";
import BuildingSwitcher from "./components/BuildingSwitcher.vue";
import Icon from "./components/Icon.vue";
import { useI18n } from "./i18n";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { ENTRY } from "./portal.js";
import {
  SECTIONS,
  allowedDomains,
  domainForSection,
  sectionsForDomain,
} from "./sections.js";
import { building, buildingLabel, clearBuilding, selectBuilding } from "./session";

const { t, lang, dir } = useI18n();

const storedCheck = createResource({
  url: "apex.habitat.api.front_desk.list_supervisor_buildings",
  onSuccess: (rows) => {
    if (!building.value) return;
    const known = (rows || []).some((row) => (row.building || row.name) === building.value);
    if (!known) clearBuilding();
  },
});

onMounted(() => {
  if (building.value) storedCheck.fetch();
});
const route = useRoute();
const router = useRouter();

const BUILDING_SECTIONS = new Set(["today", "count", "beds", "arrivals", "custody", "transfer", "safety"]);
// Sections that work against a building without owning the choice of one.
const ASSET_SECTIONS = new Set(["delivery"]);
const domains = allowedDomains();

const currentSection = computed(() => (route.meta && route.meta.section) || "");
const currentDomain = computed(
  () => (route.meta && route.meta.domain) || domainForSection(currentSection.value),
);
const usesBuilding = computed(() => BUILDING_SECTIONS.has(currentSection.value));
const showsBuilding = computed(() => usesBuilding.value || ASSET_SECTIONS.has(currentSection.value));
const needsBuilding = computed(() => usesBuilding.value && !building.value);
const portalName = computed(() =>
  ENTRY === "safety" ? t("common.safetyPortalName") : t("common.portalName"),
);

const sceneTitle = computed(() => {
  if (currentSection.value === "today") return t("today.title");
  const section = SECTIONS.find((entry) => entry.id === currentSection.value);
  return section ? t(section.labelKey) : t("common.appName");
});
const sceneEyebrow = computed(() =>
  showsBuilding.value && buildingLabel.value ? buildingLabel.value : t("common.operationalPortal"),
);
const sceneIcon = computed(() => {
  const section = SECTIONS.find((entry) => entry.id === currentSection.value);
  return section ? section.icon : "calendar";
});
const lockupVariant = computed(() => (lang.value === "ar" ? "lockup-ar" : "lockup-en"));
const sceneSubtitle = computed(() =>
  currentSection.value ? t(`scene.${currentSection.value}`) : "",
);

const subsections = computed(() => sectionsForDomain(currentDomain.value));
const WIDE_LIST_SECTIONS = new Set(["count", "delivery"]);

const showContextList = computed(() => !!currentSection.value && !needsBuilding.value);
const narrowContextList = computed(() => WIDE_LIST_SECTIONS.has(currentSection.value));
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


useDocumentLanguage(lang, dir);
</script>

<style scoped>
.console-skip {
  position: fixed;
  inset-block-start: var(--sp-3);
  inset-inline-start: var(--sp-3);
  z-index: 100;
  translate: 0 -180%;
  padding: var(--sp-2) var(--sp-4);
  border-radius: var(--radius-sm);
  background: var(--c-surface-2);
  color: var(--c-ink);
  font-weight: var(--fw-semibold);
}
.console-skip:focus {
  translate: 0;
}
.console-head-row {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  inline-size: 100%;
}
.console-identity,
.console-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  min-inline-size: 0;
}
.console-identity {
  flex: 1 1 auto;
  gap: var(--sp-4);
}
.console-actions {
  flex: 0 0 auto;
}
.brand-mark {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  padding-inline-end: var(--sp-4);
  border-inline-end: var(--border-width) solid
    color-mix(in srgb, var(--c-header-accent) 34%, transparent);
}
.brand-mark :deep(img) {
  inline-size: var(--mark);
  block-size: var(--mark);
}
.brand-copy {
  display: grid;
  min-inline-size: 0;
  overflow: hidden;
  line-height: 1.2;
}
.brand-copy strong {
  color: var(--c-header-ink);
  font-family: var(--font-display);
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  overflow-wrap: anywhere;
}
.brand-copy small {
  color: color-mix(in srgb, var(--c-header-ink) 72%, transparent);
  font-family: var(--font-serif);
  font-size: var(--fs-sm);
}
.console-scene {
  min-inline-size: 0;
  outline: none;
}
.console-scene:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: var(--sp-1);
}
.scene-heading {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: var(--sp-4);
  padding-block-end: clamp(var(--sp-5), 4vw, var(--sp-8));
  border-block-end: var(--border-width) solid var(--c-border-strong);
  margin-block-end: clamp(var(--sp-5), 3vw, var(--sp-8));
}
.scene-copy {
  min-inline-size: 0;
}
.scene-disc {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  inline-size: var(--disc);
  block-size: var(--disc);
  border-radius: var(--radius-pill);
  background: var(--c-mint);
  color: var(--c-header-bg);
}
.scene-eyebrow,
.context-kicker {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0 0 var(--sp-2);
  color: var(--c-accent-ink);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
}
.scene-eyebrow::before,
.context-kicker::before {
  content: "";
  inline-size: var(--sp-8);
  block-size: var(--border-width);
  background: currentColor;
}
.scene-heading h1 {
  max-inline-size: 22ch;
  margin: 0;
  color: var(--c-ink);
  font-family: var(--font-display);
  font-size: var(--fs-display);
  font-weight: var(--fw-heading);
  line-height: 1.12;
  text-wrap: balance;
}
.scene-subtitle,
.context-copy {
  color: var(--c-ink-soft);
  font-family: var(--font-serif);
  line-height: 1.7;
  text-wrap: pretty;
}
.scene-subtitle {
  max-inline-size: 62ch;
  margin: var(--sp-3) 0 0;
  font-size: var(--fs-body);
}
.building-stage {
  max-inline-size: 54rem;
  margin-inline: auto;
  padding-block: clamp(var(--sp-3), 3vw, var(--sp-8));
}
.stage-lockup {
  display: block;
  inline-size: clamp(var(--lockup-min), 46vw, calc(var(--lockup) * 1.5));
  block-size: auto;
  aspect-ratio: 420 / 96;
  margin-inline: auto;
  margin-block-end: clamp(var(--sp-6), 5vw, var(--sp-8));
}
.stage-kicker {
  margin: 0 0 var(--sp-2);
  padding-block-end: var(--sp-3);
  border-block-end: 1px solid var(--c-border-strong);
  color: var(--c-accent-ink);
  font-family: var(--font-brand);
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
}
.stage-title {
  margin: 0 0 var(--sp-4);
  color: var(--c-ink);
  font-family: var(--font-display);
  font-size: var(--fs-h1);
  font-weight: var(--fw-heading);
  line-height: 1.15;
  text-wrap: balance;
}
.context-nav {
  margin-block-end: clamp(var(--sp-5), 3vw, var(--sp-8));
  padding-block-end: var(--sp-4);
  border-block-end: 1px solid var(--c-border-strong);
}
.context-nav :deep(button) {
  min-block-size: var(--tap-min);
}
:deep(.mc-progress [role="progressbar"] > div) {
  background: var(--c-primary);
}
.desktop-context {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  min-inline-size: 0;
}
.desktop-context.is-narrow > .context-copy {
  display: none;
}
.desktop-context .scene-disc {
  margin-block-end: calc(-1 * var(--sp-2));
}
.desktop-context h1 {
  margin: 0;
  color: var(--c-ink);
  font-family: var(--font-display);
  font-size: var(--fs-h1);
  font-weight: var(--fw-heading);
  line-height: 1.15;
  text-wrap: balance;
}
.desktop-context.is-narrow > h1 {
  font-size: var(--fs-h2);
}
.context-copy {
  margin: calc(-1 * var(--sp-2)) 0 0;
  font-size: var(--fs-sm);
}
.context-building {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  inline-size: 100%;
  min-block-size: var(--tap-lg);
  padding-block: var(--sp-3);
  border: none;
  border-block: var(--border-width) solid var(--c-border-strong);
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}
.context-building:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: 2px;
}
.context-building-swap {
  margin-inline-start: auto;
  flex: 0 0 auto;
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-primary);
}
.context-building-icon {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  inline-size: var(--tap-min);
  block-size: var(--tap-min);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
  color: var(--c-primary);
}
.context-building > span:last-child {
  display: grid;
  min-inline-size: 0;
}
.context-building small {
  color: var(--c-muted);
  font-size: var(--fs-xs);
}
.context-building b {
  overflow: hidden;
  color: var(--c-ink);
  font-size: var(--fs-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.desktop-subnav {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.desktop-subnav a {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-block-size: var(--tap-min);
  padding-inline: var(--sp-3);
  border-radius: var(--radius-sm);
  color: var(--c-muted);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  text-decoration: none;
}
.desktop-subnav a.is-active {
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
  color: var(--c-primary);
}

@media (min-width: 64rem) {
  .has-context-list .scene-heading,
  .has-context-list .context-nav {
    display: none;
  }
  .brand-copy strong {
    font-size: var(--fs-h1);
  }
}

@media (max-width: 32rem) {
  .brand-copy small {
    display: none;
  }
  .brand-copy strong {
    font-size: var(--fs-h3);
  }
}

@media (max-width: 23rem) {
  .brand-copy {
    display: none;
  }
  .brand-mark {
    padding-inline-end: 0;
    border-inline-end: 0;
  }
}
</style>
