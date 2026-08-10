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
            <span class="pill pill-accent mt-0.5">{{ t("common.staff") }}</span>
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
      <div class="card card-pad text-center">
        <span
          class="avatar mx-auto h-12 w-12"
          style="background: color-mix(in srgb, var(--c-mint) 22%, transparent); color: var(--c-primary)"
        >
          <Icon name="user" :size="26" />
        </span>
        <div class="mt-3 text-base font-bold">
          {{ t("unlinked.hello") }}{{ ctx.full_name ? ", " + ctx.full_name : "" }}
        </div>
        <p class="mt-2 text-sm text-soft">{{ t("unlinked.notLinked") }}</p>
      </div>
      <a href="/app" class="btn btn-primary" style="text-decoration: none">
        <Icon name="external" :size="18" /> {{ t("common.goToApp") }}
      </a>
    </section>
  </div>
</template>

<script setup>
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

defineProps({ ctx: { type: Object, required: true } });
</script>
