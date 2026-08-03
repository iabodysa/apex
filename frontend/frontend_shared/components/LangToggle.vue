<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Language selector: a two-option segmented control whose labels come from the
     portal dictionary (`lang.en` / `lang.ar`). Flips the active portal language
     (and, via App.vue, the document direction). Token-driven; works on any theme.

     Shared by the driver, housing and safety portals via
     @shared/components/LangToggle.vue. `useI18n` resolves through the `@` alias to
     whichever portal bundles this file, so the toggle carries no portal-specific
     import while each portal keeps its own strings. The fleet portal (its own
     "Fleet OS" token vocabulary) and the worker portal (a >2-language <select>)
     keep their own local LangToggle — their shapes genuinely differ. -->
<template>
  <div class="lang-toggle" :class="{ 'lang-toggle-header': variant === 'header' }" role="group" :aria-label="t('lang.label')">
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
import { useI18n } from "@/i18n";

const { t, lang, setLang } = useI18n();

defineProps({
  // "header" tints the control for the dark header bar (uses header tokens).
  variant: { type: String, default: "default" },
});
</script>

<style scoped>
.lang-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: var(--sp-1);
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-ink) 8%, transparent);
}
.lang-opt {
  min-width: var(--tap-min);
  min-height: var(--tap-min);
  padding: var(--sp-1) var(--sp-3);
  border-radius: var(--radius-pill);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  line-height: 1;
  color: var(--c-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}
.lang-opt-active {
  background: var(--c-primary);
  color: var(--c-primary-ink);
}
.lang-toggle-header {
  background: color-mix(in srgb, var(--c-header-ink) 14%, transparent);
}
.lang-toggle-header .lang-opt {
  color: var(--c-header-ink);
}
.lang-toggle-header .lang-opt-active {
  background: var(--c-header-accent);
  color: var(--c-header-bg);
}
</style>
