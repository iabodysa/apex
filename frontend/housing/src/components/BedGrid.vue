<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="grid-wrap">
    <div class="legend" role="note">
      <span class="legend-item"><i class="dot dot-green"></i>{{ t("beds.free") }}</span>
      <span class="legend-item"><i class="dot dot-red"></i>{{ t("beds.taken") }}</span>
      <span class="legend-item"><i class="dot dot-amber"></i>{{ t("beds.blocked") }}</span>
      <span class="legend-item"><i class="dot dot-grey"></i>{{ t("beds.oos") }}</span>
    </div>

    <section v-for="floor in grid.floors" :key="floor.floor_label" class="floor">
      <h3 class="floor-name">
        <Icon name="layers" :size="15" />
        {{ floor.floor_label }}
      </h3>

      <article v-for="room in floor.rooms" :key="room.room" class="room-card">
        <header class="room-line">
          <span class="room-no">{{ room.room_number }}</span>
          <Button
            class="ready-chip"
            size="lg"
            variant="outline"
            :class="readinessClass(room.readiness_status)"
            :disabled="!canSetReadiness"
            :label="tEnum('readiness', room.readiness_status || 'Unknown')"
            :title="canSetReadiness ? t('beds.readiness') : t('access.needReadiness')"
            @click="$emit('room', room)"
          />
        </header>

        <div class="bed-row">
          <button
            v-for="bed in room.beds"
            :key="bed.bed"
            type="button"
            class="bed"
            :class="[bedClass(bed), { 'bed-selected': bed.bed === selectedBed }]"
            :disabled="isDisabled(bed)"
            :aria-pressed="bed.bed === selectedBed"
            :aria-label="bedLabel(bed)"
            :title="bedLabel(bed)"
            @click="$emit('bed', bed, room)"
          >
            <span class="bed-code">{{ bed.bed_code }}</span>
            <span v-if="bed.occupant" class="bed-who">{{ bed.occupant.employee_name }}</span>
            <span v-if="bed.occupant && bed.occupant.has_custody" class="bed-custody">
              <Icon name="box" :size="12" />
            </span>
          </button>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { Button } from "frappe-ui";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const props = defineProps({
  grid: { type: Object, required: true },
  selectedBed: { type: String, default: "" },
  canSetReadiness: { type: Boolean, default: false },
  freeOnly: { type: Boolean, default: false },
  occupiedOnly: { type: Boolean, default: false },
});

defineEmits(["bed", "room"]);
const { t, tEnum } = useI18n();

function bedClass(bed) {
  return "bed-" + (bed.bed_color || "grey");
}

function readinessClass(status) {
  if (status === "Ready") return "pill pill-success";
  if (status === "Needs Cleaning" || status === "Needs Repair") return "pill pill-warning";
  if (status === "Out of Service") return "pill pill-danger";
  return "pill pill-neutral";
}

function isDisabled(bed) {
  if (bed.bed_color === "grey" || bed.bed_color === "amber") return true;
  if (props.freeOnly && bed.bed_color !== "green") return true;
  if (props.occupiedOnly && bed.bed_color !== "red") return true;
  return false;
}

function bedLabel(bed) {
  if (bed.bed_color === "red") {
    const name = bed.occupant ? bed.occupant.employee_name : "";
    const held = bed.occupant && bed.occupant.has_custody ? "، " + t("beds.holdsCustody") : "";
    return t("beds.bedTaken", { name }) + held;
  }
  if (bed.bed_color === "green") return t("beds.bedFree");
  if (bed.bed_color === "amber") return t("beds.bedBlocked");
  return t("beds.bedOos");
}
</script>

<style scoped>
.grid-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--c-muted);
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
}
.dot {
  block-size: 10px;
  inline-size: 10px;
  border-radius: var(--radius-pill);
  display: inline-block;
}
.dot-green {
  background: var(--c-success);
}
.dot-red {
  background: var(--c-danger);
}
.dot-amber {
  background: var(--c-warning);
}
.dot-grey {
  background: var(--c-muted);
}

.floor {
  display: grid;
  gap: var(--sp-3);
}
.floor-name {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
  font-weight: var(--fw-heading);
  color: var(--c-muted);
}
.room-card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  min-inline-size: 0;
  padding: var(--sp-4);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius);
  background: var(--c-surface-2);
  box-shadow: var(--shadow-sm);
}
@container mc-frame (min-width: 34rem) {
  .floor {
    grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  }
  .floor-name {
    grid-column: 1 / -1;
  }
}
.room-line {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.room-no {
  flex: 1;
  min-inline-size: 0;
  font-size: var(--fs-body);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
}
.ready-chip {
  min-block-size: var(--tap-min);
}
.ready-chip:disabled {
  cursor: default;
  opacity: 0.7;
}

.bed-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  gap: var(--sp-2);
}
.bed {
  position: relative;
  min-block-size: var(--tap-lg);
  padding: var(--sp-2);
  border-radius: var(--radius-sm);
  border: 2px solid transparent;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 2px;
  cursor: pointer;
  text-align: start;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.bed:disabled {
  cursor: not-allowed;
  opacity: 0.8;
}
.bed-code {
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
}
.bed-who {
  font-size: var(--fs-xs);
  max-inline-size: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.85;
}
.bed-custody {
  position: absolute;
  inset-block-start: 4px;
  inset-inline-end: 4px;
}
.bed-green {
  background: var(--c-success-bg);
  border-color: color-mix(in srgb, var(--c-success) 45%, transparent);
  color: var(--c-success);
}
.bed-red {
  background: var(--c-danger-bg);
  border-color: color-mix(in srgb, var(--c-danger) 45%, transparent);
  color: var(--c-danger);
}
.bed-amber {
  background: var(--c-warning-bg);
  border-color: color-mix(in srgb, var(--c-warning) 45%, transparent);
  color: var(--c-warning);
}
.bed-grey {
  background: color-mix(in srgb, var(--c-ink) 7%, transparent);
  border-color: var(--c-border);
  color: var(--c-muted);
}
.bed-selected {
  outline: 3px solid var(--c-focus);
  outline-offset: 1px;
}
.bed:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: 1px;
}
@media (hover: hover) {
  .bed:hover:not(:disabled) {
    filter: brightness(0.97);
  }
}
</style>
