<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="bpass">
    <div class="bpass-band">
      <div class="bpass-band-inner">
        <div class="bpass-brand">
          <Brand variant="reverse" :size="22" />
        </div>
        <span class="bpass-kind">{{ t("boarding.title") }}</span>
      </div>
    </div>

    <div class="bpass-info">
      <div class="bpass-holder">
        <span class="bpass-avatar" aria-hidden="true">{{ holderInitial }}</span>
        <div class="bpass-holder-text">
          <span class="bpass-field-label">{{ t("boarding.holder") }}</span>
          <span class="bpass-holder-name"><bdi>{{ pass.holder_name }}</bdi></span>
        </div>
      </div>

      <div class="bpass-fields">
        <div v-if="routeLabel" class="bpass-field bpass-field-wide">
          <span class="bpass-field-label">{{ t("boarding.destination") }}</span>
          <span class="bpass-field-value"><bdi>{{ routeLabel }}</bdi></span>
        </div>
        <div v-if="departTime" class="bpass-field">
          <span class="bpass-field-label">{{ t("boarding.depart") }}</span>
          <span class="bpass-field-value"><bdi>{{ departTime }}</bdi></span>
        </div>
        <div v-if="pickupPoint" class="bpass-field">
          <span class="bpass-field-label">{{ t("boarding.pickup") }}</span>
          <span class="bpass-field-value"><bdi>{{ pickupPoint }}</bdi></span>
        </div>
      </div>
    </div>

    <div class="bpass-perf" aria-hidden="true">
      <span class="bpass-notch bpass-notch-start"></span>
      <span class="bpass-dash"></span>
      <span class="bpass-notch bpass-notch-end"></span>
    </div>

    <div class="bpass-stub">
      <p class="bpass-hint">{{ t("boarding.hint") }}</p>
      <div class="bpass-qr">
        <QrCode :value="pass.qr_payload" :size="200" :label="t('boarding.title')" themed />
      </div>
      <span class="bpass-validity">
        <Icon name="clock" :size="13" />
        {{ t("boarding.validFor", { h: pass.expires_in_hours }) }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import Brand from "@shared/components/Brand.vue";
import Icon from "./Icon.vue";
import QrCode from "./QrCode.vue";
import { useI18n } from "../i18n";

const { t, tEnum } = useI18n();

const props = defineProps({
  pass: { type: Object, required: true },
  trip: { type: Object, default: null },
});

const holderInitial = computed(
  () => (props.pass.holder_name || "?").trim().charAt(0).toUpperCase() || "?",
);

const routeLabel = computed(() => {
  if (props.pass.destination_label) return props.pass.destination_label;
  const dest = props.trip?.destination;
  if (dest) return dest.location || dest.stop_name || "";
  const trip = props.trip;
  if (!trip) return "";
  if (trip.request_type) return tEnum("requestType", trip.request_type);
  return trip.transport_request || "";
});

const departTime = computed(() => props.trip?.depart_time || "");

const pickupPoint = computed(() => {
  if (props.pass.pickup_label) return props.pass.pickup_label;
  const mp = props.trip?.my_pickup;
  if (mp) {
    return (mp.pickup && mp.pickup.building_name) || mp.accommodation_building || mp.stop_name || "";
  }
  return props.trip?.pickup_point || "";
});
</script>

<style scoped>
.bpass {
  width: 100%;
  max-width: 340px;
  margin-inline: auto;
  background: var(--c-surface);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.bpass-band {
  position: relative;
  background: var(--c-primary);
  color: var(--c-primary-ink);
  overflow: hidden;
}
.bpass-band-inner {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
}
.bpass-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.bpass-kind {
  font-size: var(--fs-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  opacity: 0.92;
  white-space: nowrap;
}

.bpass-info {
  padding: 16px 18px 14px;
}
.bpass-holder {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.bpass-avatar {
  display: grid;
  place-items: center;
  height: 42px;
  width: 42px;
  flex-shrink: 0;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-primary) 14%, transparent);
  color: var(--c-primary);
  font-weight: 800;
  font-size: 1.0625rem;
}
.bpass-holder-text {
  min-width: 0;
}
.bpass-holder-name {
  display: block;
  font-size: var(--fs-h3);
  font-weight: 800;
  color: var(--c-ink);
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bpass-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
}
.bpass-field {
  min-width: 0;
  flex: 1 1 40%;
}
.bpass-field-wide {
  flex-basis: 100%;
}
.bpass-field-label {
  display: block;
  font-size: var(--fs-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--c-muted);
  margin-bottom: 3px;
}
.bpass-field-value {
  display: block;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--c-ink);
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.bpass-perf {
  position: relative;
  display: flex;
  align-items: center;
  height: 20px;
}
.bpass-dash {
  flex: 1;
  border-top: 2px dashed var(--c-border-strong);
  margin-inline: 11px;
}
.bpass-notch {
  position: absolute;
  height: 22px;
  width: 22px;
  border-radius: var(--radius-pill);
  background: var(--c-canvas);
  border: var(--border-width) solid var(--c-border);
  top: 50%;
  transform: translateY(-50%);
}
.bpass-notch-start {
  inset-inline-start: -12px;
}
.bpass-notch-end {
  inset-inline-end: -12px;
}

.bpass-stub {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 6px 18px 20px;
}
.bpass-hint {
  font-size: var(--fs-sm);
  color: var(--c-muted);
  text-align: center;
  margin: 0;
}
.bpass-qr {
  background: var(--c-surface);
  padding: 10px;
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
}
.bpass-validity {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-xs);
  font-weight: 700;
  letter-spacing: 0.02em;
  padding: 5px 12px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-mint) 30%, transparent);
  color: var(--c-ink);
}
</style>
