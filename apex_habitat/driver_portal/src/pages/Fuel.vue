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

    <p v-if="msg" class="status-note status-ok">{{ msg }}</p>
    <p v-if="err" class="status-note status-err">{{ err }}</p>

    <!-- My fuel-request history (identity-scoped read) -->
    <section class="space-y-3">
      <h3 class="text-sm font-bold uppercase tracking-wide text-muted">{{ t("fuel.history") }}</h3>

      <LoadingState v-if="history.loading" :label="t('common.loading')" />

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
import LoadingState from "../components/LoadingState.vue";
import EmptyState from "../components/EmptyState.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n } from "../i18n";

const { t, te } = useI18n();

const litres = ref(null);
const msg = ref("");
const err = ref("");

const quota = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_fuel_quota",
  auto: true,
});
const history = createResource({
  url: "apex_habitat.salis.api.driver_portal.my_fuel_requests",
  auto: true,
});

const req = createResource({
  url: "apex_habitat.salis.api.driver_portal.submit_fuel_request",
  onSuccess: (r) => {
    msg.value = t("fuel.submitted", { name: r.name });
    err.value = "";
    litres.value = null;
    history.reload(); // new request shows in history without a manual refresh
    quota.reload();
  },
  onError: (e) => { err.value = e.messages?.[0] || t("common.error"); },
});

function submit() {
  req.submit({ litres: litres.value });
}

const quotaRow = computed(() => (quota.data?.has_quota ? quota.data : null));

// Quota bar fill: consumed as a % of the monthly allowance, clamped to [0,100]
// so an over-consumed quota still renders a full (not overflowing) bar.
const usedPct = computed(() => {
  const q = quotaRow.value;
  if (!q || !q.monthly_litres) return 0;
  return Math.min(100, Math.max(0, (q.consumed_litres / q.monthly_litres) * 100));
});

// Litres are localized for digit shaping; the unit suffix is translated.
function litreText(n) {
  const v = Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 1 });
  return `${v} ${t("fuel.litreUnit")}`;
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
</style>
