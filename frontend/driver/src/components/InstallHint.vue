<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <!-- First-visit "Add to Home Screen" hint. Shows once (dismissal persisted), and
       hides entirely once the app runs standalone. Where the browser supports a
       programmatic prompt (Chrome/Android) an Install button fires it; otherwise a
       short manual instruction is shown (iOS Safari has no install API). -->
  <div v-if="showInstallHint" class="install-hint">
    <span class="install-mark"><Icon name="download" :size="20" /></span>
    <p class="install-text">{{ canPrompt ? t("install.body") : t("install.manual") }}</p>
    <div class="install-actions">
      <Button
        v-if="canPrompt"
        class="row-btn"
        variant="solid"
        theme="green"
        :label="t('install.add')"
        @click="promptInstall"
      />
      <Button class="row-btn" variant="ghost" :label="t('install.dismiss')" @click="dismissInstallHint" />
    </div>
  </div>
</template>

<script setup>
import { Button } from "frappe-ui";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";
import { canPrompt, dismissInstallHint, promptInstall, showInstallHint } from "../pwa";

const { t } = useI18n();
</script>

<style scoped>
.install-hint {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--radius);
  border: var(--border-width) solid var(--c-border);
  background: var(--c-surface);
}
.install-mark {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  height: var(--sp-8);
  width: var(--sp-8);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
  color: var(--c-primary);
}
.install-text {
  flex: 1;
  min-width: 140px;
  font-size: var(--fs-sm);
  color: var(--c-ink-soft);
  line-height: 1.5;
}
.install-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-inline-start: auto;
}
</style>
