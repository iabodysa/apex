<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("fuel.title") }}</h2>

    <!-- This month's quota for the driver's bound vehicle. Server computes the
         remaining litres, so no client math; omitted entirely when no quota. -->
    <section v-if="quotaRow" class="card card-pad">
      <h3 class="text-sm font-bold uppercase tracking-wide text-muted mb-3">
        {{ t("fuel.quota") }}
      </h3>
      <div class="flex items-end justify-between gap-3">
        <div>
          <div class="text-2xl font-extrabold leading-none">
            <bdi>{{ litreText(quotaRow.remaining_litres) }}</bdi>
          </div>
          <div class="text-xs text-muted mt-1">{{ t("fuel.quotaRemaining") }}</div>
        </div>
        <div class="text-end text-sm">
          <div>
            <span class="text-muted">{{ t("fuel.quotaConsumed") }}:</span>
            <span class="font-semibold ms-1"><bdi>{{ litreText(quotaRow.consumed_litres) }}</bdi></span>
          </div>
          <div>
            <span class="text-muted">{{ t("fuel.quotaAllowance") }}:</span>
            <span class="font-semibold ms-1"><bdi>{{ litreText(quotaRow.monthly_litres) }}</bdi></span>
          </div>
        </div>
      </div>
      <div class="quota-track mt-3">
        <div class="quota-fill" :style="{ width: usedPct + '%' }"></div>
      </div>
    </section>

    <!-- Request fuel -->
    <section class="card card-pad space-y-4">
      <!-- What this request is: a Standard (quota-consuming) request, plus the
           approval-threshold note so the driver knows when approval kicks in. -->
      <div class="fuel-note">
        <p class="font-semibold leading-tight">{{ t("fuel.typeStandard") }}</p>
        <p class="text-sm text-muted mt-0.5">{{ t("fuel.typeStandardHint") }}</p>
        <p v-if="thresholdNote" class="text-sm text-muted mt-1">
          <Icon name="alert" :size="14" class="text-warning shrink-0 inline" /> {{ thresholdNote }}
        </p>
      </div>
      <div>
        <label class="field-label" for="fuel-litres">{{ t("fuel.litres") }}</label>
        <input
          id="fuel-litres"
          v-model.number="litres"
          type="number"
          min="1"
          inputmode="numeric"
          :placeholder="t('fuel.placeholder')"
          class="input"
        />
      </div>
      <button class="btn btn-primary" :disabled="req.loading || !litres" @click="submit">
        <Icon name="fuel" :size="20" /> {{ t("fuel.submit") }}
      </button>
    </section>

    <!-- My fuel-request history (identity-scoped read) -->
    <section class="space-y-3">
      <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("fuel.history") }}</h3>

      <Skeleton v-if="history.loading" :rows="3" />

      <ErrorState v-else-if="history.error" :message="t('errors.loadFailed')" @retry="history.reload()" />

      <EmptyState
        v-else-if="!history.data || !history.data.length"
        icon="fuel"
        :title="t('fuel.historyEmpty')"
        :hint="t('fuel.historyEmptyHint')"
      />

      <template v-else>
        <div v-for="r in history.data" :key="r.name" class="card card-pad">
          <div class="flex items-start justify-between gap-2">
            <div class="font-bold leading-tight">
              <bdi>{{ litreText(r.requested_litres) }}</bdi>
            </div>
            <span class="pill shrink-0" :class="statusPill(r.status)">{{ te("fuelStatus", r.status) }}</span>
          </div>
          <div class="mt-1 flex items-center gap-2 text-sm text-muted">
            <Icon name="calendar" :size="16" class="text-primary shrink-0" />
            <span><bdi>{{ r.request_date || "—" }}</bdi></span>
            <span v-if="r.fuel_platform" class="text-muted">·</span>
            <span v-if="r.fuel_platform"><bdi>{{ r.fuel_platform }}</bdi></span>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";

const { t, te, n } = useI18n();

const litres = ref(null);

const quota = createResource({
  url: "apex.salis.api.driver_portal.my_fuel_quota",
  auto: true,
});
const history = createResource({
  url: "apex.salis.api.driver_portal.my_fuel_requests",
  auto: true,
});

const req = createResource({
  url: "apex.salis.api.driver_portal.submit_fuel_request",
  onSuccess: (r) => {
    pushToast(t("fuel.submitted", { name: r.name }), "ok");
    litres.value = null;
    history.reload(); // new request shows in history without a manual refresh
    quota.reload();
  },
  onError: (e) => { pushToast(e.messages?.[0] || t("common.error"), "err"); },
});

function submit() {
  req.submit({ litres: litres.value });
}

const quotaRow = computed(() => (quota.data?.has_quota ? quota.data : null));

// Approval-threshold copy: server returns the Salis Settings litre threshold on
// the quota read (present even with no quota). 0/blank means no threshold, so the
// note is omitted. Litres are locale-shaped to match the rest of the screen.
const thresholdNote = computed(() => {
  const lt = quota.data?.approval_threshold_litres;
  if (!lt || Number(lt) <= 0) return null;
  return t("fuel.approvalThreshold", { litres: litreText(lt) });
});

// Quota bar fill: consumed as a % of the monthly allowance, clamped to [0,100]
// so an over-consumed quota still renders a full (not overflowing) bar.
const usedPct = computed(() => {
  const q = quotaRow.value;
  if (!q || !q.monthly_litres) return 0;
  return Math.min(100, Math.max(0, (q.consumed_litres / q.monthly_litres) * 100));
});

// Litres localized for digit shaping (Intl, active-locale keyed); unit translated.
function litreText(v) {
  return `${n(Number(v || 0), { maximumFractionDigits: 1 })} ${t("fuel.litreUnit")}`;
}

// Map a Fuel Request status to a status pill (purely cosmetic).
function statusPill(status) {
  const s = (status || "").toLowerCase();
  if (s === "approved" || s === "done") return "pill-success";
  if (s === "pending") return "pill-warning";
  if (s === "failed" || s === "reverted" || s === "cancelled") return "pill-danger";
  return "pill-accent";
}
</script>

<style scoped>
.quota-track {
  height: 8px;
  border-radius: 999px;
  background: var(--c-border, rgba(0, 0, 0, 0.08));
  overflow: hidden;
}
.quota-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--c-primary, #2563eb);
  transition: width 0.3s ease;
}
.fuel-note {
  padding: 12px;
  border-radius: var(--radius, 12px);
  background: color-mix(in srgb, var(--c-mint, #d1fae5) 25%, transparent);
}
</style>
