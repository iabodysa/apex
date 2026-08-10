<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <dl class="veh-facts">
    <div v-for="fact in shown" :key="fact.key">
      <dt>
        <slot name="icon" :fact="fact" />
        {{ fact.label }}
      </dt>
      <dd :class="{ 'is-num': fact.numeric, 'is-late': fact.tone === 'late', 'is-soon': fact.tone === 'soon' }">
        <bdi dir="auto">{{ fact.value }}</bdi>
        <span v-if="fact.suffix" class="veh-suffix">{{ fact.suffix }}</span>
      </dd>
    </div>
  </dl>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  facts: { type: Array, default: () => [] },
  emptyValue: { type: String, default: "—" },
});

const shown = computed(() =>
  props.facts
    .filter((fact) => fact && fact.label)
    .map((fact) => ({
      key: fact.key || fact.label,
      label: fact.label,
      value: fact.value == null || fact.value === "" ? props.emptyValue : fact.value,
      suffix: fact.suffix || "",
      numeric: !!fact.numeric,
      tone: fact.tone || "",
      icon: fact.icon || "",
    })),
);
</script>

<style scoped>
.veh-facts {
  display: grid;
  gap: var(--sp-3);
  margin: 0;
}
.veh-facts > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
}
.veh-facts dt {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  color: var(--c-muted);
  font-size: var(--fs-sm);
}
.veh-facts dd {
  margin: 0;
  font-weight: var(--fw-semibold);
  text-align: end;
  overflow-wrap: anywhere;
}
.veh-facts dd.is-num {
  font-variant-numeric: tabular-nums;
}
.veh-facts dd.is-late {
  color: var(--c-danger);
}
.veh-facts dd.is-soon {
  color: var(--c-warning);
}
.veh-suffix {
  margin-inline-start: var(--sp-1);
  color: var(--c-muted);
  font-weight: var(--fw-body);
}
</style>
