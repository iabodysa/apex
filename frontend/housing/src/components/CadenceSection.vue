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
          <Icon name="calendar" :size="12" /> {{ periodLabel }}
        </span>
      </span>
      <ProgressRing :done="ratedCount" :total="block.tasks.length" :size="52" />
      <span class="cadence-chevron" :class="{ 'cadence-chevron-open': open }">
        <Icon name="chevron" :size="18" />
      </span>
    </button>

    <Transition name="rows">
      <div v-show="open" class="cadence-rows">
        <button
          v-if="ratedCount"
          type="button"
          class="cadence-toggle"
          @click="hideSettled = !hideSettled"
        >
          {{ hideSettled ? t("round.due.showSettled", { n: ratedCount }) : t("round.due.hideSettled") }}
        </button>

        <TaskRow
          v-for="task in visibleTasks"
          :key="task.name"
          :ref="(el) => registerRow(task.name, el)"
          :task="task"
          :verdict="(ratings[task.name] || {}).verdict || ''"
          :notes="(ratings[task.name] || {}).notes || ''"
          :photo="(ratings[task.name] || {}).photo || ''"
          :settled="isSettled(task.name)"
          @rate="(v) => onRate(task.name, v)"
          @note="(n) => $emit('note', block.cadence, task.name, n)"
          @photo="(p) => $emit('photo', block.cadence, task.name, p)"
          @reopen="reopened = task.name"
        />
      </div>
    </Transition>
  </section>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
import Icon from "./Icon.vue";
import ProgressRing from "./ProgressRing.vue";
import TaskRow from "./TaskRow.vue";
import { useI18n } from "../i18n";

const props = defineProps({
  block: { type: Object, required: true },
  ratings: { type: Object, default: () => ({}) },
});

const emit = defineEmits(["rate", "note", "photo"]);
const { t, tEnum, lang } = useI18n();

const periodLabel = computed(() => {
  const p = props.block.period || {};
  const locale = lang.value === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-US";
  const num = (n) => new Intl.NumberFormat(locale, { useGrouping: false }).format(n);
  if (p.kind === "day") return t("round.period.today");
  if (p.kind === "week") return t("round.period.thisWeek");
  if (p.kind === "month") {
    const month = new Intl.DateTimeFormat(locale, { month: "long" }).format(
      new Date(Date.UTC(p.year, p.month - 1, 1)),
    );
    return `${month} ${num(p.year)}`;
  }
  if (p.kind === "quarter") return t("round.period.quarter", { n: num(p.quarter), year: num(p.year) });
  if (p.kind === "year") return num(p.year);
  return "";
});

const open = ref(true);
const hideSettled = ref(false);
const reopened = ref("");
const rows = new Map();

function registerRow(name, el) {
  if (el) rows.set(name, el);
  else rows.delete(name);
}

function isSettled(name) {
  if (reopened.value === name) return false;
  return !!(props.ratings[name] || {}).verdict;
}

const visibleTasks = computed(() =>
  hideSettled.value ? props.block.tasks.filter((t) => !isSettled(t.name)) : props.block.tasks,
);

function onRate(name, verdict) {
  if (reopened.value === name) reopened.value = "";
  emit("rate", props.block.cadence, name, verdict);
  if (!verdict) return;
  nextTick(() => {
    const next = props.block.tasks.find((t) => !(props.ratings[t.name] || {}).verdict);
    const el = next && rows.get(next.name);
    const node = el && (el.$el || el);
    if (node && node.scrollIntoView) {
      node.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "center" });
    }
  });
}

function reduceMotion() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

const ratedCount = computed(
  () => props.block.tasks.filter((t) => (props.ratings[t.name] || {}).verdict).length,
);

watch(
  () => ratedCount.value === props.block.tasks.length && props.block.tasks.length > 0,
  (complete, was) => {
    if (complete && !was) open.value = false;
  },
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
  border-block: 1px solid var(--c-border-strong);
  background: transparent;
  overflow: hidden;
}
.cadence-head {
  display: flex;
  align-items: center;
  gap: 12px;
  inline-size: 100%;
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
  block-size: 38px;
  inline-size: 38px;
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
  min-inline-size: 0;
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

.cadence-toggle {
  display: block;
  inline-size: 100%;
  min-block-size: var(--tap-min);
  padding: var(--sp-2) var(--sp-3);
  border-block-end: 1px solid var(--c-border);
  color: var(--c-primary);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  text-align: start;
  cursor: pointer;
}
.cadence-rows {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-block-end: var(--sp-3);
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
