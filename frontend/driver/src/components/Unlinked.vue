<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="mx-auto w-full px-6 py-7" style="max-width: 480px">
    <section v-if="ctx.is_staff" class="space-y-5">
      <div class="card card-pad">
        <div class="flex items-center gap-3">
          <span
            class="avatar h-11 w-11"
            style="background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary)"
          >
            <Icon name="user" :size="22" />
          </span>
          <div class="min-w-0">
            <div class="text-base font-bold truncate">{{ ctx.full_name || t("common.staff") }}</div>
            <StatusLabel class="mt-0.5" :label="t('common.staff')" tone="accent" />
          </div>
        </div>
        <p class="mt-3 text-sm text-soft">{{ t("unlinked.staffHint") }}</p>
      </div>

      <div v-if="ctx.links && ctx.links.length" class="space-y-3">
        <a
          v-for="link in ctx.links"
          :key="link.url"
          :href="link.url"
          class="card card-pad flex items-center gap-3"
          style="text-decoration: none"
        >
          <span
            class="avatar h-9 w-9"
            style="border-radius: var(--radius-sm); background: var(--c-ink); color: var(--c-surface)"
          >
            <Icon name="dashboard" :size="18" />
          </span>
          <span class="font-semibold">{{ link.label }}</span>
          <Icon name="chevron" :size="18" class="ml-auto text-muted" />
        </a>
      </div>
    </section>

    <section v-else class="space-y-5">
      <EmptyState
        :title="t('unlinked.hello') + (ctx.full_name ? ', ' + ctx.full_name : '')"
        :hint="t('unlinked.notLinked')"
      >
        <template #icon><Icon name="user" :size="22" /></template>
        <template #action>
          <a href="/app" class="btn btn-primary" style="text-decoration: none">
            <Icon name="external" :size="18" /> {{ t("common.goToApp") }}
          </a>
        </template>
      </EmptyState>
    </section>
  </div>
</template>

<script setup>
import EmptyState from "@shared/components/EmptyState.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

defineProps({ ctx: { type: Object, required: true } });
</script>
