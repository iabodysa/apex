<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="card card-pad text-center">
    <div
      class="avatar mx-auto mb-3 h-12 w-12"
      style="background: var(--c-danger-bg); color: var(--c-danger)"
    >
      <Icon name="alert" :size="26" />
    </div>
    <p class="font-bold mb-1">{{ message || t("errors.loadFailed") }}</p>
    <button
      class="btn btn-primary mt-4"
      style="width: auto; padding-inline: 24px"
      @click="$emit('retry')"
    >
      {{ t("common.retry") }}
    </button>
  </div>
</template>

<script setup>
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

defineProps({
  message: { type: String, default: "" },
});

defineEmits(["retry"]);
</script>
