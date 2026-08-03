<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <Panel :title="t('home.today')">
    <template #status>
      <Badge class="tone-badge" :theme="theme" variant="subtle" size="lg" :label="stateLabel" />
    </template>

    <p v-if="!attendance.check_in" class="shift-line">{{ t("home.notCheckedIn") }}</p>

    <dl v-else class="shift-times">
      <div class="shift-time">
        <dt>{{ t("attendance.checkIn") }}</dt>
        <dd><bdi>{{ fmtTime(attendance.check_in) }}</bdi></dd>
      </div>
      <div v-if="attendance.check_out" class="shift-time">
        <dt>{{ t("attendance.checkOut") }}</dt>
        <dd><bdi>{{ fmtTime(attendance.check_out) }}</bdi></dd>
      </div>
      <div v-if="attendance.worked_hours != null" class="shift-time">
        <dt>{{ t("attendance.hoursPresent") }}</dt>
        <dd><bdi>{{ n(attendance.worked_hours) }}</bdi></dd>
      </div>
    </dl>
  </Panel>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";
import Panel from "@shared/components/Panel.vue";
import { useI18n } from "../i18n";
import { shiftStep } from "../today";

const { t, n, fmtTime } = useI18n();

const props = defineProps({
  today: { type: Object, required: true },
});

const attendance = computed(() => props.today.attendance || {});
const step = computed(() => shiftStep(props.today));

const theme = computed(() => (step.value === "notCheckedIn" ? "gray" : "green"));

const stateLabel = computed(() => {
  if (step.value === "done") return t("attendance.checkedOutLabel");
  if (step.value === "working") return t("attendance.checkedInLabel");
  return t("attendance.notCheckedIn");
});
</script>

<style scoped>
.shift-line {
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.3;
}
.shift-times {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-5);
  margin-top: var(--sp-3);
}
.shift-time dt {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
  letter-spacing: 0.02em;
}
.shift-time dd {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
}
</style>
