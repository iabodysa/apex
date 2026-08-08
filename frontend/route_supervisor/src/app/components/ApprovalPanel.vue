<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="panel">
    <header class="panel-head">
      <div>
        <h2 class="panel-title">{{ t("approval.status") }}</h2>
        <p class="panel-sub">{{ statusHint }}</p>
      </div>
    </header>

    <div class="approval-body">
      <div class="status-block" :class="'sb-' + plan.approval.toLowerCase()">
        <Icon :name="statusIcon" :size="30" :stroke-width="1.8" />
        <div>
          <div class="sb-label">{{ t("approval." + plan.approval) }}</div>
          <div v-if="plan.decided_on" class="sb-sub">
            {{ t("approval.decidedOn", { at: agoLabel(plan.decided_on, lang) }) }}
          </div>
        </div>
      </div>

      <div v-if="plan.approval === 'Rejected' && plan.rejection_reason" class="reason-box">
        <span class="rb-label">{{ t("approval.reason") }}</span>
        <p>{{ plan.rejection_reason }}</p>
      </div>

      <div v-if="plan.approval === 'Pending'" class="approve-actions">
        <Button
          variant="solid"
          theme="green"
          size="xl"
          :loading="busy"
          :loading-text="t('approval.approving')"
          :label="t('approval.approve')"
          @click="approvePlan(plan.name)"
        >
          <template #prefix><Icon name="check" :size="17" /></template>
        </Button>
        <Button
          variant="outline"
          theme="red"
          size="xl"
          :disabled="busy"
          :label="t('approval.reject')"
          @click="requestReject(plan.name)"
        >
          <template #prefix><Icon name="x" :size="17" /></template>
        </Button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";

import Icon from "../Icon.vue";
import { agoLabel } from "../fmt.js";
import { useActions } from "../actions.js";
import { usePlans } from "../usePlans.js";
import { useI18n } from "@/i18n";

const props = defineProps({
  plan: { type: Object, required: true },
});

const { t, lang } = useI18n();
const { busy } = usePlans();
const { approvePlan, requestReject } = useActions();

const statusHint = computed(() =>
  props.plan.approval === "Pending" ? t("approval.pendingHint") : t("approval." + props.plan.approval),
);
const statusIcon = computed(
  () => ({ Pending: "clock", Approved: "circle-check", Rejected: "x" })[props.plan.approval] || "clock",
);
</script>
