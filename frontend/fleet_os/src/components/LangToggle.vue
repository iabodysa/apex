<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Language selector (English / Arabic). Flips the portal language and, via
     App.vue, the document direction. Token-driven to fit the Fleet OS topbar.

     [#a281] DELIBERATELY NOT @shared/components/LangToggle.vue, unlike the fleet,
     driver, safety and route_supervisor portals. WHAT WOULD BREAK IF MERGED:
     this file is styled from the legacy short-name token vocabulary (--bg3, --b1,
     --blue, --r2, --r3, --t3), which is defined ONLY in this portal's
     src/index.css — the shared component is written against the --c-* design
     system, which this portal's stylesheet does not define. Swapping it would
     leave every one of those declarations invalid at computed-value time, and it
     would also resize the control to the shared 44px touch target inside a dense
     26px supervisor topbar. fleet_os is the preserved-verbatim rollback copy of
     the supervisor board (see vite.config.js), so its chrome must not drift. -->
<template>
  <div class="lang-toggle" role="group" :aria-label="t('lang.label')">
    <button
      type="button"
      class="lang-opt"
      :class="{ 'lang-opt-active': lang === 'en' }"
      :aria-pressed="lang === 'en'"
      :title="t('lang.english')"
      @click="setLang('en')"
    >
      {{ t("lang.en") }}
    </button>
    <button
      type="button"
      class="lang-opt"
      :class="{ 'lang-opt-active': lang === 'ar' }"
      :aria-pressed="lang === 'ar'"
      :title="t('lang.arabic')"
      @click="setLang('ar')"
    >
      {{ t("lang.ar") }}
    </button>
  </div>
</template>

<script setup>
import { useI18n } from "../i18n";

const { t, lang, setLang } = useI18n();
</script>

<style scoped>
.lang-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: var(--r2);
  background: var(--bg3);
  border: 1px solid var(--b1);
  flex-shrink: 0;
}
.lang-opt {
  min-width: 32px;
  min-height: 26px;
  padding: 3px 9px;
  border-radius: var(--r3);
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  color: var(--t3);
  background: transparent;
  border: none;
  cursor: pointer;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}
.lang-opt-active {
  background: var(--blue);
  color: #fff;
}
</style>
