<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <Panel v-if="quotaRow" :title="t('fuel.quota')">
      <div class="flex items-end justify-between gap-3">
        <div>
          <div class="text-2xl font-bold leading-none">
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
    </Panel>

    <section class="card card-pad space-y-4">
      <div class="fuel-note">
        <p class="font-semibold leading-tight">{{ t("fuel.typeStandard") }}</p>
        <p class="text-sm text-muted mt-0.5">{{ t("fuel.typeStandardHint") }}</p>
        <p v-if="thresholdNote" class="text-sm text-muted mt-1">
          <Icon name="alert" :size="14" class="text-warning shrink-0 inline" /> {{ thresholdNote }}
        </p>
      </div>
      <FormControl
        v-model="litres"
        type="number"
        size="lg"
        :min="1"
        inputmode="numeric"
        :label="t('fuel.litres')"
        :placeholder="t('fuel.placeholder')"
      />
    </section>

    <Panel :title="t('fuel.history')">
      <Skeleton v-if="history.loading" :rows="3" />

      <LoadError
        v-else-if="history.error"
        :title="t('errors.loadFailed')"
        :detail="historyErrorMessage"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="history.reload()"
      />

      <EmptyState
        v-else-if="!history.data || !history.data.length"
        :title="t('fuel.historyEmpty')"
        :hint="t('fuel.historyEmptyHint')"
      >
        <template #icon><Icon name="fuel" :size="22" /></template>
      </EmptyState>

      <template v-else>
        <div v-for="r in history.data" :key="r.name" class="card card-pad">
          <div class="flex items-start justify-between gap-2">
            <div class="font-bold leading-tight">
              <bdi>{{ litreText(r.requested_litres) }}</bdi>
            </div>
            <StatusLabel class="shrink-0" :label="te('fuelStatus', r.status)" :tone="statusTone(r.status)" />
          </div>
          <div class="mt-1 flex items-center gap-2 text-sm text-muted">
            <Icon name="calendar" :size="16" class="text-primary shrink-0" />
            <span><bdi>{{ r.request_date || "—" }}</bdi></span>
            <span v-if="r.fuel_platform" class="text-muted">·</span>
            <span v-if="r.fuel_platform"><bdi>{{ r.fuel_platform }}</bdi></span>
          </div>
        </div>
      </template>
    </Panel>

    <ActionDock>
      <template #primary>
        <Button
          class="dock-btn"
          variant="solid"
          theme="green"
          size="2xl"
          :disabled="req.loading || !litres"
          :loading="req.loading"
          :label="t('fuel.submit')"
          @click="submit"
        >
          <template #prefix><Icon name="fuel" :size="20" /></template>
        </Button>
      </template>
    </ActionDock>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { Button, FormControl, createResource } from "frappe-ui";
import ActionDock from "@shared/components/ActionDock.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import Panel from "@shared/components/Panel.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import Icon from "../components/Icon.vue";
import Skeleton from "../components/Skeleton.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
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

const historyErrorMessage = computed(() =>
  resourceErrorMessage(history.error, "errors.loadFailed"),
);

const req = createResource({
  url: "apex.salis.api.driver_portal.submit_fuel_request",
  onSuccess: (r) => {
    pushToast(t("fuel.submitted", { name: r.name }), "ok");
    litres.value = null;
    history.reload();
    quota.reload();
  },
  onError: (e) => { pushToast(e.messages?.[0] || t("common.error"), "err"); },
});

function submit() {
  req.submit({ litres: Number(litres.value) });
}

const quotaRow = computed(() => (quota.data?.has_quota ? quota.data : null));

const thresholdNote = computed(() => {
  const lt = quota.data?.approval_threshold_litres;
  if (!lt || Number(lt) <= 0) return null;
  return t("fuel.approvalThreshold", { litres: litreText(lt) });
});

const usedPct = computed(() => {
  const q = quotaRow.value;
  if (!q || !q.monthly_litres) return 0;
  return Math.min(100, Math.max(0, (q.consumed_litres / q.monthly_litres) * 100));
});

function litreText(v) {
  return `${n(Number(v || 0), { maximumFractionDigits: 1 })} ${t("fuel.litreUnit")}`;
}

function statusTone(status) {
  const s = (status || "").toLowerCase();
  if (s === "approved" || s === "done") return "success";
  if (s === "pending") return "warning";
  if (s === "failed" || s === "reverted" || s === "cancelled") return "danger";
  return "accent";
}
</script>

<style scoped>
.quota-track {
  height: 8px;
  border-radius: var(--radius-pill);
  background: var(--c-border);
  overflow: hidden;
}
.quota-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--c-primary);
  transition: width 0.3s ease;
}
.fuel-note {
  padding: 12px;
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--c-mint) 25%, transparent);
}
</style>
