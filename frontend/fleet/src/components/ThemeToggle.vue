<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="emp-theme" role="group" :aria-label="t('emp.theme.label')">
    <button
      v-for="m in modes"
      :key="m"
      type="button"
      class="emp-theme-opt"
      :class="{ on: mode === m }"
      :aria-pressed="mode === m"
      @click="setMode(m)"
    >
      <Icon :name="icons[m]" :size="13" />
      <span>{{ t('emp.theme.' + m) }}</span>
    </button>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();
const STORAGE_KEY = "apex_theme";
const modes = ["light", "auto", "dark"];
const icons = { light: "circle-dot", auto: "settings", dark: "circle-check" };
const mode = ref("auto");

function apply(m) {
  const root = document.documentElement;
  if (m === "auto") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", m);
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
  if (!modes.includes(saved)) saved = "auto";
  mode.value = saved;
  apply(saved);
});
</script>

<style scoped>
.emp-theme {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-header-ink) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-header-ink) 20%, transparent);
  flex-shrink: 0;
}
.emp-theme-opt {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 44px;
  padding: 4px 10px;
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
}
.emp-theme-opt.on {
  background: var(--c-header-accent);
  color: var(--forest);
}
@media (max-width: 480px) {
  .emp-theme-opt span {
    display: none;
  }
  .emp-theme-opt {
    min-width: 44px;
    justify-content: center;
  }
}
</style>
