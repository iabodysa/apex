<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <article class="card-artefact">
    <header class="card-artefact-head">
      <Brand variant="reverse" :size="30" />
      <div class="card-artefact-title">
        <small>{{ t("arrivals.slipTitle") }}</small>
        <b>{{ card.worker_name }}</b>
      </div>
    </header>

    <div class="card-artefact-body">
      <img v-if="card.qr" class="card-artefact-qr" :src="card.qr" alt="" />
      <dl class="card-artefact-fields">
        <template v-for="row in fields" :key="row.key">
          <dt>{{ row.label }}</dt>
          <dd><bdi dir="auto">{{ row.value }}</bdi></dd>
        </template>
      </dl>
    </div>

    <footer class="card-artefact-foot">{{ t("common.signature") }}</footer>
  </article>
</template>

<script setup>
import { computed } from "vue";
import Brand from "@shared/components/Brand.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const props = defineProps({
  card: { type: Object, required: true },
});

const fields = computed(() => {
  const rows = [
    ["building", t("arrivals.cardBuilding"), props.card.building],
    ["bed", t("arrivals.cardBed"), props.card.bed],
    ["project", t("arrivals.cardProject"), props.card.project],
    ["check_in_date", t("arrivals.cardCheckIn"), props.card.check_in_date],
    ["designation", t("arrivals.cardDesignation"), props.card.designation],
    ["passport_number", t("arrivals.passport"), props.card.passport_number],
    ["iqama_number", t("arrivals.iqama"), props.card.iqama_number],
    ["nationality", t("arrivals.nationality"), props.card.nationality],
  ];
  return rows
    .filter(([, , value]) => value)
    .map(([key, label, value]) => ({ key, label, value }));
});
</script>

<style scoped>
.card-artefact {
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius);
  background: var(--c-surface);
  overflow: hidden;
}
.card-artefact-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-4);
  background: var(--c-header-bg);
  color: var(--c-header-ink);
}
.card-artefact-title {
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
}
.card-artefact-title small {
  font-size: var(--fs-sm);
  opacity: 0.75;
}
.card-artefact-title b {
  font-size: var(--fs-h2);
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.card-artefact-body {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-4);
  padding: var(--sp-4);
}
.card-artefact-qr {
  flex: 0 0 auto;
  inline-size: 116px;
  block-size: 116px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  background: #fff;
}
.card-artefact-fields {
  flex: 1;
  min-inline-size: 0;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--sp-2) var(--sp-3);
  margin: 0;
}
.card-artefact-fields dt {
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.card-artefact-fields dd {
  margin: 0;
  font-weight: var(--fw-semibold);
  overflow-wrap: anywhere;
}
.card-artefact-foot {
  padding: var(--sp-3) var(--sp-4);
  border-block-start: 1px solid var(--c-border);
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
@media print {
  .card-artefact {
    border-color: #000;
  }
}
</style>
