<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <ListSkeleton :rows="rows" :label="label || t('common.loading')" />
</template>

<script setup>
import ListSkeleton from "@shared/components/ListSkeleton.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

defineProps({
  label: { type: String, default: "" },
  rows: { type: Number, default: 4 },
});
</script>
