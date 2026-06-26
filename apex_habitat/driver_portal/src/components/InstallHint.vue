<template>
  <!-- First-visit "Add to Home Screen" hint. Shows once (dismissal persisted), and
       hides entirely once the app runs standalone. Where the browser supports a
       programmatic prompt (Chrome/Android) an Install button fires it; otherwise a
       short manual instruction is shown (iOS Safari has no install API). -->
  <div v-if="showInstallHint" class="card card-pad install-hint">
    <div class="flex items-start gap-3">
      <span class="avatar h-10 w-10 shrink-0" style="background: var(--c-primary); color: var(--c-primary-ink)">
        <Icon name="download" :size="20" />
      </span>
      <div class="min-w-0 flex-1">
        <p class="font-bold leading-tight">{{ t("install.title") }}</p>
        <p class="text-sm text-muted mt-0.5">
          {{ canPrompt ? t("install.body") : t("install.manual") }}
        </p>
        <div class="mt-3 flex items-center gap-2">
          <button v-if="canPrompt" class="btn btn-primary" style="width: auto; padding-inline: 18px" @click="onInstall">
            <Icon name="download" :size="18" /> {{ t("install.add") }}
          </button>
          <button class="btn btn-outline" style="width: auto; padding-inline: 16px" @click="dismissInstallHint">
            {{ t("install.dismiss") }}
          </button>
        </div>
      </div>
      <button class="install-x" :aria-label="t('install.dismiss')" @click="dismissInstallHint">
        <Icon name="x" :size="18" />
      </button>
    </div>
  </div>
</template>

<script setup>
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";
import { canPrompt, dismissInstallHint, promptInstall, showInstallHint } from "../pwa";

const { t } = useI18n();

function onInstall() {
  promptInstall();
}
</script>

<style scoped>
.install-hint {
  border: var(--border-width, 1px) solid var(--c-primary, #00844e);
}
.install-x {
  color: var(--c-ink-soft, #777);
  align-self: flex-start;
  padding: 2px;
}
</style>
