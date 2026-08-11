<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="sk-status" role="status" :aria-label="label || t('common.loading')">
    <div v-if="variant === 'stats'" class="grid gap-3" :class="`grid-cols-${lines}`" aria-hidden="true">
      <div v-for="n in lines" :key="n" class="stat">
        <div class="sk-line sk-w-50" style="height: 10px"></div>
        <div class="sk-line sk-w-70" style="height: 18px; margin-top: 8px"></div>
      </div>
    </div>

    <div v-else-if="variant === 'lines'" class="space-y-3" aria-hidden="true">
      <div v-for="n in lines" :key="n" class="sk-line" :class="n === lines && lines > 1 ? 'sk-w-60' : ''"></div>
    </div>

    <div v-else class="card card-pad" aria-hidden="true">
      <div class="flex items-center gap-3">
        <div class="sk-block sk-avatar"></div>
        <div class="min-w-0 flex-1 space-y-2">
          <div class="sk-line sk-w-70"></div>
          <div class="sk-line sk-w-40"></div>
        </div>
      </div>
      <div class="space-y-3" style="margin-top: 16px">
        <div v-for="n in lines" :key="n" class="sk-line" :class="n === lines && lines > 1 ? 'sk-w-60' : ''"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from "../i18n";

const { t } = useI18n();

defineProps({
  variant: { type: String, default: "card" },
  lines: { type: Number, default: 3 },
  label: { type: String, default: "" },
});
</script>
