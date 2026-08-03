<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="lang-toggle" :class="{ 'lang-toggle-header': variant === 'header' }">
    <Icon name="globe" :size="16" class="lang-globe shrink-0" aria-hidden="true" />
    <select
      class="lang-select"
      :value="lang"
      :aria-label="t('lang.label')"
      @change="setLang($event.target.value)"
    >
      <option v-for="code in SUPPORTED" :key="code" :value="code">{{ LANG_NAMES[code] }}</option>
    </select>
  </div>
</template>

<script setup>
import Icon from "./Icon.vue";
import { useI18n, SUPPORTED, LANG_NAMES } from "../i18n";

const { t, lang, setLang } = useI18n();

defineProps({
  variant: { type: String, default: "default" },
});
</script>

<style scoped>
.lang-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-ink) 8%, transparent);
}
.lang-globe {
  color: var(--c-muted);
}
.lang-select {
  /* --tap-min is the DESIGN.md §8 floor in BOTH dimensions. The comment above this
     rule claimed the 44px target while the value under it was 38px — measured at
     390px, this was the smallest control anywhere in the portal. */
  min-height: var(--tap-min);
  min-width: var(--tap-min);
  padding: 4px 6px;
  border: none;
  background: transparent;
  color: var(--c-ink);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  line-height: 1;
  cursor: pointer;
  appearance: none;
}
.lang-select:focus-visible {
  outline: 2px solid var(--c-primary);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

/* The "header" variant sits on the dark header bar, so it takes the header tokens
   rather than the page ones; every other surface uses the default. */
.lang-toggle-header {
  background: color-mix(in srgb, var(--c-header-ink) 14%, transparent);
}
.lang-toggle-header .lang-globe,
.lang-toggle-header .lang-select {
  color: var(--c-header-ink);
}
.lang-toggle-header .lang-select option {
  color: var(--c-ink);
}
</style>
