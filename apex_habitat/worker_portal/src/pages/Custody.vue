<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("custody.title") }}</h2>

    <!-- Stale note when rendering the last-known cached snapshot offline. -->
    <div v-if="isStale" class="stale-note">
      <Icon name="alert" :size="14" class="shrink-0" />
      <span>{{ t("common.stale") }}</span>
    </div>

    <template v-if="cus.loading && !cd">
      <Skeleton :lines="3" />
      <Skeleton :lines="3" />
    </template>

    <!-- Error with NO cached fallback: an invalid/disabled token (PermissionError)
         or a server failure must NOT masquerade as a benign "no custody" empty
         state. With a cached snapshot we render it (labelled stale) instead. -->
    <div v-else-if="cus.error && !cd" class="card card-pad text-center">
      <p class="text-sm font-bold mb-1">{{ t("errors.loadError") }}</p>
      <p class="text-sm text-muted">{{ errorMessage }}</p>
      <button class="btn btn-primary mt-3" style="width: auto; padding-inline: 24px" @click="cus.reload()">
        {{ t("common.retry") }}
      </button>
    </div>

    <template v-else-if="items.length">
      <!-- One card per held article -->
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

      <!-- The acknowledgment Web Form lives outside the SPA, so this is a plain
           link, not a router-link. -->
      <a :href="ackUrl" class="btn btn-outline" style="text-decoration: none">
        <Icon name="check" :size="18" /> {{ t("custody.acknowledge") }}
      </a>
    </template>

    <div v-else class="card card-pad text-center">
      <p class="text-sm text-muted">{{ t("custody.empty") }}</p>
      <p class="text-xs text-muted mt-1">{{ t("custody.emptyHint") }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, h, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { formatDate } from "../datetime";
import { TOKEN } from "../token";
import { cacheGet, cacheSet } from "../cache";

const { t } = useI18n();

// Cache the last good custody read so an offline drop renders it
// stale-but-labelled instead of an error (mirrors the driver portal pattern).
const CACHE_KEY = "get_worker_custody";
const staleCus = ref(null);
const cus = createResource({
  url: "apex_habitat.salis.api.masar.get_worker_custody",
  params: { token: TOKEN },
  auto: true,
  onSuccess: (r) => {
    staleCus.value = null;
    cacheSet(CACHE_KEY, r);
  },
  onError: () => {
    const cached = cacheGet(CACHE_KEY);
    if (cached) staleCus.value = cached;
  },
});

const errorMessage = computed(() => resourceErrorMessage(cus.error));

// Live data when present; otherwise the cached snapshot (offline).
const cd = computed(() => cus.data || staleCus.value?.data || null);
const isStale = computed(() => !cus.data && !!staleCus.value);

const items = computed(() => cd.value?.items || []);

// Frappe Web Form route (outside the SPA); the holder picks the issue there.
const ackUrl = "/my-custody-acknowledgment";

function fmtQty(n) {
  const v = Number(n) || 0;
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

const Row = (rprops) =>
  h("div", { class: "flex items-center gap-2" }, [
    h(Icon, { name: rprops.icon, size: 18, class: "text-primary shrink-0" }),
    h("dt", { class: "text-muted" }, rprops.label),
    // <bdi> isolates Latin/numeric values (received date) inside the RTL row;
    // a no-op for Arabic/text values. [T-313]
    h("dd", { class: "ms-auto font-semibold" }, h("bdi", null, rprops.value || t("common.none"))),
  ]);
</script>

<style scoped>
.stale-note {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius, 12px);
  font-size: 0.8125rem;
  font-weight: 600;
  background: var(--c-warning-bg, #fef3c7);
  color: var(--c-warning, #92400e);
}
</style>
