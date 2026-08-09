<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="lang-toggle" :class="{ 'lang-toggle-header': variant === 'header' }" role="group" :aria-label="t('lang.label')">
    <Button
      type="button"
      class="lang-opt"
      variant="ghost"
      size="xl"
      :class="{ 'lang-opt-active': lang === 'en' }"
      :label="t('lang.en')"
      :aria-pressed="lang === 'en'"
      :title="t('lang.english')"
      @click="setLang('en')"
    />
    <Button
      type="button"
      class="lang-opt"
      variant="ghost"
      size="xl"
      :class="{ 'lang-opt-active': lang === 'ar' }"
      :label="t('lang.ar')"
      :aria-pressed="lang === 'ar'"
      :title="t('lang.arabic')"
      @click="setLang('ar')"
    />
  </div>
</template>

<script setup>
import { Button } from "frappe-ui";
import { useI18n } from "@/i18n";

const { t, lang, setLang } = useI18n();

defineProps({
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
  min-inline-size: var(--tap-min);
  min-block-size: var(--tap-min);
  border-radius: var(--radius-pill);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  line-height: 1;
  color: var(--c-muted);
  background: transparent;
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
