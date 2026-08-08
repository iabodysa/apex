<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <EmptyState :title="t('access.title')" :hint="t('access.hint')">
    <template #icon><Icon name="alert" :size="24" /></template>
    <template v-if="fallback" #action>
      <Button size="xl" variant="outline" :label="t('access.goBack')" @click="goBack" />
    </template>
  </EmptyState>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { Button } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import { useI18n } from "../i18n";
import { allowedSections } from "../sections.js";

const { t } = useI18n();
const router = useRouter();

const fallback = computed(() => allowedSections()[0] || null);

function goBack() {
  if (fallback.value) router.replace(fallback.value.path);
}
</script>
