<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("custody.title") }}</h2>

    <template v-if="cus.loading && !cd">
      <Skeleton :lines="3" />
      <Skeleton :lines="3" />
    </template>

    <div v-else-if="cus.error && !cd" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("errors.loadError") }}</p>
      <p class="text-sm text-muted">{{ errorMessage }}</p>
      <button class="btn btn-primary mt-3" style="width: auto; padding-inline: 24px" @click="cus.reload()">
        {{ t("common.retry") }}
      </button>
    </div>

    <template v-else-if="items.length">
      <section v-for="(it, i) in items" :key="i" class="card card-pad">
        <div class="flex items-center gap-3">
          <span class="avatar h-11 w-11" style="background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary)">
            <Icon name="briefcase" :size="22" />
          </span>
          <div class="min-w-0 flex-1">
            <div class="text-base font-extrabold leading-tight truncate">
              {{ it.item_name || it.item }}
            </div>
            <div v-if="it.building" class="text-sm text-muted truncate">{{ it.building }}</div>
          </div>
          <div class="text-end shrink-0">
            <div class="text-lg font-extrabold leading-none">{{ fmtQty(it.qty) }}</div>
            <div class="text-xs text-muted">{{ it.uom || t("custody.qty") }}</div>
          </div>
        </div>

        <dl class="space-y-3 text-sm mt-4">
          <Row v-if="it.received_date" icon="calendar" :label="t('custody.receivedDate')" :value="formatDate(it.received_date)" />
          <Row icon="user" :label="t('custody.issuedBy')" :value="it.issued_by" />
          <Row v-if="it.building" icon="building" :label="t('custody.building')" :value="it.building" />
        </dl>
      </section>
    </template>

    <div v-else class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("custody.empty") }}</p>
      <p class="text-xs text-muted mt-1">{{ t("custody.emptyHint") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, h } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatDate } from "../utils/datetime";

const { t } = useI18n();

const cus = createResource({
  url: "apex.salis.api.masar.get_worker_custody",
  auto: true,
});

const errorMessage = computed(() => resourceErrorMessage(cus.error));

const cd = computed(() => cus.data || null);

const items = computed(() => cd.value?.items || []);

function fmtQty(n) {
  const v = Number(n) || 0;
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

const Row = (rprops) =>
  h("div", { class: "flex items-center gap-2" }, [
    h(Icon, { name: rprops.icon, size: 18, class: "text-primary shrink-0" }),
    h("dt", { class: "text-muted" }, rprops.label),
    h("dd", { class: "ms-auto font-semibold" }, h("bdi", null, rprops.value || t("common.none"))),
  ]);
</script>

