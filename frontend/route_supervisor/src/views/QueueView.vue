<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="work work-single">
    <section class="queue">
      <header class="queue-head">
        <h2>{{ t("queue.title") }}</h2>
        <p>{{ t("queue.subtitle", { n: pendingPlans.length }) }}</p>
      </header>

      <div v-if="loadState === 'loading'" class="plan-skel" aria-hidden="true">
        <div v-for="n in 3" :key="n" class="skeleton-card" />
      </div>

      <LoadError
        v-else-if="loadState === 'error'"
        :title="t('list.loadError')"
        :detail="loadError"
        :hint="t('list.loadErrorHint')"
        :retry-label="t('common.retry')"
        @retry="load()"
      />

      <EmptyState
        v-else-if="!pendingPlans.length"
        :title="t('queue.empty')"
        :hint="t('queue.emptyHint')"
      >
        <template #icon><Icon name="circle-check" :size="20" :stroke-width="1.6" /></template>
      </EmptyState>

      <ul v-else class="queue-list">
        <li v-for="plan in pendingPlans" :key="plan.name" class="queue-row">
          <router-link
            class="queue-open"
            :to="{ name: 'plan', params: { name: plan.name, tab: 'approval' } }"
          >
            <span class="qr-name">{{ plan.route_name || plan.name }}</span>
            <span class="qr-meta">
              <span v-if="plan.project"><Icon name="badge" :size="12" /> {{ plan.project }}</span>
              <span v-if="plan.shift"><Icon name="clock" :size="12" /> {{ t("shift." + plan.shift) }}</span>
              <span><Icon name="pin" :size="12" /> {{ t("list.stops", { n: plan.total_stops }) }}</span>
              <span v-if="plan.driver"><Icon name="user" :size="12" /> {{ plan.driver }}</span>
              <span v-if="plan.vehicle"><Icon name="truck" :size="12" /> {{ plan.vehicle }}</span>
            </span>
          </router-link>
          <!-- Deciding a card never moves the selection: the supervisor keeps his place in the
               queue he is working through. -->
          <div class="qr-actions">
            <Button
              variant="solid"
              theme="green"
              size="xl"
              :disabled="busy"
              :label="t('approval.approve')"
              @click="approvePlan(plan.name)"
            >
              <template #prefix><Icon name="check" :size="16" /></template>
            </Button>
            <Button
              variant="outline"
              theme="red"
              size="xl"
              :disabled="busy"
              :label="t('approval.reject')"
              @click="requestReject(plan.name)"
            >
              <template #prefix><Icon name="x" :size="16" /></template>
            </Button>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { Button } from "frappe-ui";

import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";

import Icon from "../Icon.vue";
import { useActions } from "../actions.js";
import { usePlans } from "../usePlans.js";
import { useI18n } from "@/i18n";

const { t } = useI18n();
const { pendingPlans, loadState, loadError, busy, load } = usePlans();
const { approvePlan, requestReject } = useActions();
</script>
