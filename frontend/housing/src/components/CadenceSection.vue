<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <section class="cadence">
    <button type="button" class="cadence-head" @click="open = !open">
      <span class="cadence-badge" :class="badgeClass">
        <Icon :name="badgeIcon" :size="18" />
      </span>
      <span class="cadence-titles">
        <span class="cadence-name">{{ tEnum("cadence", block.cadence) }}</span>
        <span class="cadence-period">
          <Icon name="calendar" :size="12" /> {{ block.period_label }}
        </span>
      </span>
      <ProgressRing :done="ratedCount" :total="block.tasks.length" :size="52" />
      <span class="cadence-chevron" :class="{ 'cadence-chevron-open': open }">
        <Icon name="chevron" :size="18" />
      </span>
    </button>

    <Transition name="rows">
      <div v-show="open" class="cadence-rows">
        <TaskRow
          v-for="task in block.tasks"
          :key="task.name"
          :task="task"
          :verdict="(ratings[task.name] || {}).verdict || ''"
          :notes="(ratings[task.name] || {}).notes || ''"
          :photo="(ratings[task.name] || {}).photo || ''"
          @rate="(v) => $emit('rate', block.cadence, task.name, v)"
          @note="(n) => $emit('note', block.cadence, task.name, n)"
          @photo="(p) => $emit('photo', block.cadence, task.name, p)"
        />
      </div>
    </Transition>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import Icon from "./Icon.vue";
import ProgressRing from "./ProgressRing.vue";
import TaskRow from "./TaskRow.vue";
import { useI18n } from "../i18n";

const props = defineProps({
  block: { type: Object, required: true },
  ratings: { type: Object, default: () => ({}) },
});

defineEmits(["rate", "note", "photo"]);
const { tEnum } = useI18n();

const open = ref(true);

const ratedCount = computed(
  () => props.block.tasks.filter((t) => (props.ratings[t.name] || {}).verdict).length,
);

const badgeIcon = computed(() => {
  switch (props.block.cadence) {
    case "Daily":
      return "shield";
    case "Weekly":
      return "clipboard-check";
    case "Monthly":
      return "calendar";
    default:
      return "shield-check";
  }
});
const badgeClass = computed(() => "badge-" + props.block.cadence.toLowerCase());
</script>

<style scoped>
.cadence {
  border-radius: var(--radius-lg);
  border: 1px solid var(--c-border);
  background: var(--c-surface);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.cadence-head {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: start;
}
@media (hover: hover) {
  .cadence-head:hover {
    background: color-mix(in srgb, var(--c-ink) 4%, transparent);
  }
}
.cadence-badge {
  display: grid;
  place-items: center;
  height: 38px;
  width: 38px;
  border-radius: var(--radius);
  flex-shrink: 0;
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 12%, transparent);
}
.badge-weekly {
  color: var(--c-warning);
  background: color-mix(in srgb, var(--c-warning) 14%, transparent);
}
.badge-monthly,
.badge-quarterly,
.badge-annual {
  color: var(--c-ink);
  background: color-mix(in srgb, var(--c-ink) 9%, transparent);
}
.cadence-titles {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cadence-name {
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.1;
}
.cadence-period {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
}
.cadence-chevron {
  color: var(--c-muted);
  transition: transform 0.25s ease;
  flex-shrink: 0;
}
.cadence-chevron-open {
  transform: rotate(90deg);
}
:global([dir="rtl"] .cadence-chevron) {
  transform: scaleX(-1);
}
:global([dir="rtl"] .cadence-chevron-open) {
  transform: scaleX(-1) rotate(90deg);
}

.cadence-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0 12px 14px;
}

.rows-enter-active,
.rows-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.25s ease;
}
.rows-enter-from,
.rows-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
