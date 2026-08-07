<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="detail">
    <header class="detail-head">
      <div class="detail-id">
        <p class="detail-label">{{ t("delivery.asset") }}</p>
        <bdi v-if="heading" class="detail-serial mono">
          {{ delivery.asset_serial_number || delivery.name }}
        </bdi>
        <bdi v-if="heading ? delivery.asset_serial_number : true" class="detail-sub mono">
          {{ delivery.name }}
        </bdi>
      </div>
      <Badge :theme="released ? 'green' : 'orange'" size="lg" :label="statusLabel">
        <template #prefix><Icon :name="released ? 'key' : 'truck'" :size="16" /></template>
      </Badge>
    </header>

    <dl class="route">
      <div class="route-leg">
        <dt class="route-key">{{ t("delivery.from") }}</dt>
        <dd class="route-val">{{ delivery.from_building || t("common.none") }}</dd>
      </div>
      <div class="route-leg">
        <dt class="route-key">{{ t("delivery.to") }}</dt>
        <dd class="route-val">{{ delivery.to_building || t("common.none") }}</dd>
      </div>
    </dl>

    <ol class="gate-track" :aria-label="t('delivery.trackLabel')">
      <li
        v-for="g in gateList"
        :key="g.n"
        class="gate"
        :class="`gate-${g.state}`"
        :aria-current="g.state === 'current' ? 'step' : undefined"
      >
        <span class="gate-bar"></span>
        <span class="gate-name">
          <Icon v-if="g.state === 'cleared'" name="check" :size="16" />
          {{ g.label }}
        </span>
        <span class="sr-only">{{ t("delivery.gate." + g.state) }}</span>
      </li>
    </ol>

    <ErrorMessage v-if="error" :message="error" />
  </div>
</template>

<script setup>
import { computed } from "vue";
import { Badge, ErrorMessage } from "frappe-ui";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";
import { gates } from "../gates";

const { t } = useI18n();

const props = defineProps({
  delivery: { type: Object, required: true },
  error: { type: String, default: "" },
  heading: { type: Boolean, default: true },
});

const released = computed(() => props.delivery.status === "Released");
const statusLabel = computed(() =>
  released.value ? t("delivery.readyToReceive") : t("delivery.awaitingExits"),
);
const gateList = computed(() => gates(props.delivery, (n) => t("delivery.exit" + n)));
</script>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.detail-head {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
}
.detail-id {
  flex: 1;
  min-width: 0;
}
.detail-label {
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.detail-serial {
  display: block;
  margin-top: var(--sp-1);
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  overflow-wrap: anywhere;
}
.detail-sub {
  display: block;
  margin-top: var(--sp-1);
  font-size: var(--fs-sm);
  color: var(--c-muted);
  overflow-wrap: anywhere;
}

.route {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
  margin: 0;
  padding: var(--sp-3);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-ink) 4%, transparent);
}
.route-key {
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.route-val {
  margin: 0;
  margin-top: var(--sp-1);
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  overflow-wrap: anywhere;
}

.gate-track {
  display: flex;
  gap: var(--sp-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.gate {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.gate-bar {
  height: var(--sp-2);
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-ink) 14%, transparent);
}
.gate-name {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  line-height: 1.3;
  color: var(--c-muted);
}
.gate-cleared .gate-bar {
  background: var(--c-success);
}
.gate-cleared .gate-name {
  color: var(--c-success);
}
.gate-current .gate-bar {
  background: var(--c-primary);
}
.gate-current .gate-name {
  color: var(--c-ink);
  font-weight: var(--fw-heading);
}
</style>
