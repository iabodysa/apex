<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="approval-review">
    <header class="section-heading">
      <p>{{ t("approval.eyebrow") }}</p>
      <h3>{{ t("approval.status") }}</h3>
      <span>{{ statusHint }}</span>
    </header>

    <div class="approval-status" :data-tone="statusTone">
      <Icon :name="statusIcon" :size="28" :stroke-width="1.7" />
      <div>
        <strong>{{ t("approval." + plan.approval) }}</strong>
        <span v-if="plan.decided_on">
          {{ t("approval.decidedOn", { at: agoLabel(plan.decided_on, lang) }) }}
        </span>
      </div>
    </div>

    <div v-if="plan.approval === 'Rejected' && plan.rejection_reason" class="rejection-reason">
      <span>{{ t("approval.reason") }}</span>
      <p>{{ plan.rejection_reason }}</p>
    </div>

    <ActionDock v-if="plan.approval === 'Pending'">
      <template #primary>
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
      </template>
      <template #danger>
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
      </template>
    </ActionDock>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";

import ActionDock from "@shared/components/ActionDock.vue";

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
const statusTone = computed(
  () => ({ Pending: "warning", Approved: "success", Rejected: "danger" })[props.plan.approval] || "neutral",
);
</script>
