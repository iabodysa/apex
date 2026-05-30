<!-- Language selector: EN | ع. Flips the active portal language (and, via App.vue,
     the document direction). Token-driven segmented control; works on any theme. -->
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
import { useI18n } from "../i18n";

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
  padding: 3px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-ink) 8%, transparent);
}
.lang-opt {
  min-width: 34px;
  min-height: 28px;
  padding: 4px 10px;
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

/* Header variant: sits on the dark header bar — use header tokens so it reads. */
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
