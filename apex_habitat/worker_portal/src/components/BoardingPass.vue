<!-- A real boarding-pass / ticket card for the worker's signed QR. Two stubs split
     by a perforated divider: an INFO stub (brand band + holder + labelled trip
     fields) and a QR stub on a clean white card. All colors are theme tokens so
     the pass adapts to afmco / frappe / dark; the QR keeps its own white bg +
     quiet zone (non-negotiable for scanning) regardless of theme. -->
<template>
  <div class="bpass">
    <!-- Accent header band: brand mark + "Boarding Pass" title. -->
    <div class="bpass-band">
      <div class="bpass-band-arc" aria-hidden="true"><Brand mode="arc" /></div>
      <div class="bpass-band-inner">
        <div class="bpass-brand">
          <Brand mode="mark" :size="22" />
          <span class="bpass-brand-name">AFMCO</span>
        </div>
        <span class="bpass-kind">{{ t("boarding.title") }}</span>
      </div>
    </div>

    <!-- Holder + labelled trip fields. -->
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

    <!-- Perforated divider: a dashed line with a notch cut into each edge. -->
    <div class="bpass-perf" aria-hidden="true">
      <span class="bpass-notch bpass-notch-start"></span>
      <span class="bpass-dash"></span>
      <span class="bpass-notch bpass-notch-end"></span>
    </div>

    <!-- QR stub: the scannable code on its own clean white card. -->
    <div class="bpass-stub">
      <p class="bpass-hint">{{ t("boarding.hint") }}</p>
      <div class="bpass-qr">
        <QrCode :value="pass.qr_payload" :size="200" :label="t('boarding.title')" />
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
import Brand from "./Brand.vue";
import Icon from "./Icon.vue";
import QrCode from "./QrCode.vue";
import { useI18n } from "../i18n";

const { t, tEnum } = useI18n();

const props = defineProps({
  // The boarding-pass payload: qr_payload, holder_name, expires_in_hours,
  // destination_label (the route drop-off) and pickup_label (the worker's own
  // building) — both worker-scoped server-side, NOT the generic pickup_point.
  pass: { type: Object, required: true },
  // The trip this pass is for, for the labelled ticket fields (route/time/pickup).
  trip: { type: Object, default: null },
});

const holderInitial = computed(
  () => (props.pass.holder_name || "?").trim().charAt(0).toUpperCase() || "?",
);

// Destination = the route's actual drop-off (the server resolves it to the final
// stop's location/name), NOT the worker's own pickup. Falls back to the worker's
// trip destination stop, then the localized trip type, then the request id.
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

// Pickup point = the worker's OWN building/stop (server-resolved), not the generic
// per-request pickup_point. Falls back to the trip's my_pickup building, then the
// request's pickup_point as a last resort.
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
  /* The ticket: a rounded surface card with an accent band on top. overflow-hidden
     keeps the band's rounded top corners clean; max-width keeps it phone-sized. */
  width: 100%;
  max-width: 340px;
  margin-inline: auto;
  background: var(--c-surface);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg, var(--shadow));
  overflow: hidden;
}

/* Accent header band. */
.bpass-band {
  position: relative;
  background: var(--c-primary);
  color: var(--c-primary-ink);
  overflow: hidden;
}
.bpass-band-arc {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.5;
}
.bpass-band-arc :deep(svg) {
  position: absolute;
  inset-inline-end: -24px;
  top: 50%;
  transform: translateY(-50%);
  height: 180%;
  width: auto;
  color: var(--c-primary-ink);
  opacity: 0.18;
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
.bpass-brand-name {
  font-size: 1.0625rem;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.bpass-kind {
  font-size: var(--fs-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  opacity: 0.92;
  white-space: nowrap;
}

/* Info stub. */
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

/* Labelled ticket fields — wrap so nothing overflows on a narrow phone. */
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

/* Perforated divider between the info and the QR stub. */
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
  /* Cut a circle out of each edge by painting the page canvas color over it. */
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

/* QR stub. */
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
  /* Always a clean white frame around the QR — the code itself stays white-bg +
     4-module quiet zone (QrCode.vue) so it scans on any theme, including dark. */
  background: #fff;
  padding: 10px;
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg, 0 2px 10px rgba(0, 0, 0, 0.12));
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
