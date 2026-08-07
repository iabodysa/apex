<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="theme-toggle" role="group" :aria-label="t('theme.label')">
    <button
      v-for="m in MODES"
      :key="m"
      type="button"
      class="theme-opt"
      :class="{ 'theme-opt-active': mode === m }"
      :aria-pressed="mode === m"
      :aria-label="t('theme.' + m)"
      @click="setMode(m)"
    >
      <IconBase :shape="ICONS[m]" :size="13" :align="true" />
      <span>{{ t("theme." + m) }}</span>
    </button>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import IconBase from "./IconBase.vue";
import { circleCheck, circleDot, settings } from "./icons.js";
import { useI18n } from "@/i18n";

const { t } = useI18n();

const STORAGE_KEY = "apex_theme";
const MODES = ["light", "auto", "dark"];
const ICONS = { light: circleDot, auto: settings, dark: circleCheck };

const SERVER_THEME =
  typeof document === "undefined" ? null : document.documentElement.getAttribute("data-theme");

const mode = ref("auto");

function apply(m) {
  const root = document.documentElement;
  if (m !== "auto") root.setAttribute("data-theme", m);
  else if (SERVER_THEME === null) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", SERVER_THEME);
}

function setMode(m) {
  mode.value = m;
  apply(m);
  try {
    localStorage.setItem(STORAGE_KEY, m);
  } catch (e) {
  }
}

onMounted(() => {
  let saved = "auto";
  try {
    saved = localStorage.getItem(STORAGE_KEY) || "auto";
  } catch (e) {
  }
  if (!MODES.includes(saved)) saved = "auto";
  mode.value = saved;
  apply(saved);
});
</script>

<style scoped>
.theme-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-header-ink) 9%, transparent);
  border: var(--border-width) solid color-mix(in srgb, var(--c-header-ink) 20%, transparent);
  flex-shrink: 0;
}
.theme-opt {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: var(--tap-min);
  padding: var(--sp-1) 10px;
  border: none;
  border-radius: var(--radius-pill);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-semibold);
  line-height: 1;
  cursor: pointer;
  color: color-mix(in srgb, var(--c-header-ink) 72%, transparent);
  background: transparent;
  transition: background 0.15s ease, color 0.15s ease;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.theme-opt-active {
  background: var(--c-header-accent);
  color: var(--c-header-bg);
}
.theme-opt:focus-visible {
  outline: 3px solid var(--c-header-accent);
  outline-offset: 2px;
}
.theme-opt:disabled {
  opacity: 0.45;
  cursor: default;
}
@media (max-width: 480px) {
  .theme-opt span {
    display: none;
  }
  .theme-opt {
    min-width: var(--tap-min);
    justify-content: center;
  }
}
</style>
