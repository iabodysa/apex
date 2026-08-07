<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="text-muted text-sm">{{ label || t("common.loading") }}</div>
</template>

<script setup>
import { useI18n } from "../i18n";

const { t } = useI18n();

defineProps({
  label: { type: String, default: "" },
});
</script>
