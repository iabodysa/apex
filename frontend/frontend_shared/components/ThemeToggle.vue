<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Light / Auto / Dark switch, shared by every portal.

     Writes data-theme onto <html>; the shared tokens.css explicit-toggle rules
     win over prefers-color-scheme in both directions, so a pinned choice sticks.
     Sits on the forest header, so it reads light-on-dark next to LangToggle.

     "AUTO" RESTORES THE SERVER'S VALUE — IT DOES NOT REMOVE THE ATTRIBUTE.
     Four wrappers server-render data-theme="{{ portal_theme or 'afmco' }}", so a
     toggle that removed the attribute would silently discard an administrator's
     theme the first time a worker tapped Auto, and it could never be recovered
     without a reload. Restoring the rendered value is also what makes Auto mean
     auto: "afmco" is the default-identity alias and the shared auto-dark
     allow-list follows the OS through it exactly like an absent attribute.

     `useI18n` resolves through the `@` alias to whichever portal bundles this
     file — the only portal-local import, which is what keeps it barrel-safe.
     Portals supply `theme.label`, `theme.light`, `theme.auto`, `theme.dark`. -->
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
      <!-- Hidden below --bp-phone, where the glyph is all that is left. The label
           above carries the same string, so the button never loses its name. -->
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

// Read at module scope, before any click can write: this is the wrapper's value,
// not one this control produced.
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
    /* private-mode / storage disabled — the in-memory choice still applies */
  }
}

onMounted(() => {
  let saved = "auto";
  try {
    saved = localStorage.getItem(STORAGE_KEY) || "auto";
  } catch (e) {
    /* ignore */
  }
  if (!MODES.includes(saved)) saved = "auto";
  mode.value = saved;
  apply(saved);
});
</script>

<style scoped>
/* Padding is 2px, not the shared LangToggle's 3px, because this group also carries a
   1px border: 2+1 per side matches the switcher's 3, so at the same --tap-min option
   height the two header controls come out exactly the same height. */
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
  /* --tap-min: the accessible touch target the shared LangToggle beside it uses.
     This control sits on the same worker-facing header, so it may not be smaller. */
  min-height: var(--tap-min);
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
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.theme-opt-active {
  background: var(--c-header-accent);
  color: var(--c-header-bg);
}
/* The shared ring is tuned against the page ground; on forest chrome the header
   accent is the one that stays visible. */
.theme-opt:focus-visible {
  outline: 3px solid var(--c-header-accent);
  outline-offset: 2px;
}
.theme-opt:disabled {
  opacity: 0.45;
  cursor: default;
}
/* On phones the label hides, leaving just the glyph — which would shrink the button
   below the touch target on the axis the label was holding open. 480px = --bp-phone
   (frontend_shared/tokens.css); keep in sync. */
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
