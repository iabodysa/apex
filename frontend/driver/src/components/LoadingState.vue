<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <!-- Shared loading row. Mirrors the per-page inline loading style
       (muted small text). Optional `label` overrides the default key. -->
  <div class="text-muted text-sm">{{ label || t("common.loading") }}</div>
</template>

<script setup>
import { useI18n } from "../i18n";

const { t } = useI18n();

defineProps({
  // Caller-provided text. Falls back to the shared common.loading key.
  label: { type: String, default: "" },
});
</script>
