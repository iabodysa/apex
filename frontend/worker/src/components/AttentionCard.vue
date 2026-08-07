<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <Panel :title="t('home.alerts')">
    <template #status>
      <Badge class="tone-badge" theme="orange" variant="subtle" size="lg" :label="String(alerts.length)" />
    </template>

    <ul class="doc-rows">
      <li v-for="doc in alerts" :key="doc.type" class="doc-row">
        <div class="doc-line">
          <span class="doc-mark" :class="'mark-' + tone(doc)">
            <Icon name="doc" :size="20" />
          </span>
          <span class="doc-label">{{ t("profile." + doc.type) }}</span>
          <Badge
            class="tone-badge"
            :theme="tone(doc) === 'danger' ? 'red' : 'orange'"
            variant="subtle"
            size="md"
            :label="badge(doc)"
          />
        </div>

        <div v-if="doc.type === 'iqama'" class="doc-action">
          <p v-if="notified" class="doc-done">
            <Icon name="check" :size="16" />
            <span>{{ t("home.notifyHrDone") }}</span>
          </p>
          <template v-else>
            <Button
              class="row-btn"
              variant="outline"
              :disabled="notifying || !inWindow(doc)"
              :label="notifying ? t('home.notifyHrSending') : t('home.notifyHr')"
              @click="$emit('notify')"
            >
              <template #prefix><Icon name="send" :size="16" /></template>
            </Button>
            <p v-if="!inWindow(doc)" class="row-reason">
              {{ t("home.notifyHrWindow", { n: windowDays }) }}
            </p>
          </template>
          <p v-if="error" class="doc-error">{{ error }}</p>
        </div>
      </li>
    </ul>
  </Panel>
</template>

<script setup>
import { Badge, Button } from "frappe-ui";
import Panel from "@shared/components/Panel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const props = defineProps({
  alerts: { type: Array, required: true },
  windowDays: { type: Number, required: true },
  notifying: { type: Boolean, default: false },
  notified: { type: Boolean, default: false },
  error: { type: String, default: "" },
});

defineEmits(["notify"]);

function tone(doc) {
  return doc.days_left != null && doc.days_left < 0 ? "danger" : "warning";
}

function badge(doc) {
  if (doc.days_left != null && doc.days_left < 0) return t("home.alertExpired");
  return t("home.alertDaysLeft", { n: doc.days_left });
}

function inWindow(doc) {
  return doc.days_left != null && doc.days_left <= props.windowDays;
}
</script>

<style scoped>
.doc-rows {
  display: flex;
  flex-direction: column;
}
.doc-row {
  padding-block: var(--sp-3);
  border-top: var(--border-width) solid var(--c-border);
}
.doc-row:first-child {
  border-top: none;
  padding-top: 0;
}
.doc-line {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-height: var(--tap-md);
}
.doc-mark {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  height: var(--sp-8);
  width: var(--sp-8);
  border-radius: var(--radius-sm);
}
.mark-warning {
  background: var(--c-warning-bg);
  color: var(--c-warning);
}
.mark-danger {
  background: var(--c-danger-bg);
  color: var(--c-danger);
}
.doc-label {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  line-height: 1.4;
}
.doc-action {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-2);
  margin-top: var(--sp-2);
}
.doc-done {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: var(--tap-md);
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-success);
}
.doc-error {
  font-size: var(--fs-sm);
  color: var(--c-danger);
  line-height: 1.5;
}
</style>
