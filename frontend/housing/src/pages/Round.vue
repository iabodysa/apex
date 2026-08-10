<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <ListSkeleton v-if="dueRes.loading && !due.length" :rows="5" :label="t('common.loading')" />

  <LoadError
    v-else-if="dueRes.error"
    :title="t('errors.roundFailed')"
    :detail="dueErrorMessage"
    :hint="t('errors.retryHint')"
    :retry-label="t('common.retry')"
    @retry="load()"
  />

  <template v-else-if="submitted">
    <div class="done">
      <div class="done-mark"><Icon name="check" :size="34" /></div>
      <h2 class="section-title">
        {{ submitted.ratified ? t("round.success.title") : t("round.success.draftTitle") }}
      </h2>
      <p class="section-sub">
        {{ submitted.ratified ? t("round.success.subtitle") : t("round.success.draftHint") }}
      </p>

      <p
        v-if="submitted.ratified"
        class="status-note"
        :class="submitted.emailed ? 'status-ok' : 'status-warn'"
      >
        {{ submitted.emailed ? t("round.success.emailed") : t("round.success.notEmailed") }}
      </p>

      <div
        v-if="submitted.ratified && submitted.rounds && submitted.rounds.length"
        class="stack-tight results"
      >
        <p class="results-head">{{ t("round.success.results") }}</p>
        <div
          v-for="r in submitted.rounds"
          :key="r.cadence + r.safety_round"
          class="result-row"
        >
          <span class="result-cadence">{{ tEnum("cadence", r.cadence) }}</span>
          <Badge :theme="resultTheme(r.overall_result)" size="lg" :label="tEnum('result', r.overall_result)" />
        </div>
      </div>

      <div v-if="submitted.failed && submitted.failed.length" class="stack-tight results">
        <p class="results-head">{{ t("round.success.partial") }}</p>
        <p class="hint">{{ t("round.success.partialHint") }}</p>
        <div v-for="f in submitted.failed" :key="f.cadence" class="result-row result-failed">
          <span class="result-cadence">{{ tEnum("cadence", f.cadence) }}</span>
          <span class="result-reason">{{ f.message }}</span>
        </div>
      </div>

      <Button size="2xl" variant="outline" class="wide" :label="t('round.success.another')" @click="resetAll" />
    </div>
  </template>

  <EmptyState
    v-else-if="!due.length"
    :title="t('round.empty.title')"
    :hint="t('round.empty.subtitle')"
  >
    <template #icon><Icon name="shield-check" :size="24" /></template>
    <template #action>
      <Button size="xl" variant="outline" :label="t('round.empty.switch')" @click="changeBuilding" />
    </template>
  </EmptyState>

  <template v-else>
    <div class="due-intro">
      <h2 class="section-title">{{ t("round.due.title") }}</h2>
      <p class="section-sub">{{ t("round.due.subtitle") }}</p>
      <p class="draft-note"><Icon name="shield" :size="13" /> {{ t("round.due.draftKept") }}</p>
    </div>

    <div v-if="staleOffer" class="stale">
      <p class="stale-title">{{ t("round.stale.title") }}</p>
      <p class="hint">{{ t("round.stale.body") }}</p>
      <div class="stale-actions">
        <Button size="lg" variant="solid" :label="t('round.stale.reload')" @click="acceptStale" />
        <Button size="lg" variant="outline" :label="t('round.stale.dismiss')" @click="staleOffer = false" />
      </div>
    </div>

    <CadenceSection
      v-for="block in due"
      :key="block.cadence"
      :block="block"
      :ratings="ratings[block.cadence] || {}"
      @rate="onRate"
      @note="onNote"
      @photo="onPhoto"
    />

    <div class="hz-dock">
      <ErrorMessage v-if="submitError" class="dock-error" :message="submitError" />
      <Button
        class="dock-btn"
        size="2xl"
        variant="solid"
        theme="green"
        :disabled="totalRated === 0 || !canSubmit"
        :loading="submitRes.loading"
        :loading-text="t('round.submit.sending')"
        :label="canRatify ? t('round.submit.cta') : t('round.submit.ctaDraft')"
        @click="doSubmit"
      >
        <template #prefix><Icon name="send" :size="20" /></template>
      </Button>
      <p class="dock-hint">{{ dockHint }}</p>
    </div>
  </template>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { Badge, Button, ErrorMessage, createResource } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import CadenceSection from "../components/CadenceSection.vue";
import Icon from "../components/Icon.vue";
import ListSkeleton from "../components/ListSkeleton.vue";
import LoadError from "../components/LoadError.vue";
import { useI18n, apiErrorMessage, resourceErrorMessage } from "../i18n";
import { can } from "../portal.js";
import { connectSafetyRealtime } from "../realtime.js";
import { dropRoundDraft, readRoundDraft, writeRoundDraft } from "../drafts.js";
import { building, clearBuilding, forgetMissingBuilding, localDate } from "../session";

const { t, tEnum } = useI18n();

const STATUS = { pass: "Good", fail: "Not Done", issue: "Poor" };

const canRatify = can("submit_round");
const canSubmit = canRatify || can("record_round");

const ratings = reactive({});
const submitted = ref(null);
const submitError = ref("");
const staleOffer = ref(false);

const dueRes = createResource({
  url: "apex.habitat.api.safety_checklist.get_due_cadences",
  makeParams: () => ({ building: building.value }),
  onError: (error) => forgetMissingBuilding(error),
});

const submitRes = createResource({
  url: "apex.habitat.api.safety_checklist.submit_due_rounds",
});

const due = computed(() => (dueRes.data && dueRes.data.due) || []);
const dueErrorMessage = computed(() => resourceErrorMessage(dueRes.error, "errors.roundFailed"));

const totalRated = computed(() => {
  let n = 0;
  for (const cadence of Object.keys(ratings)) {
    for (const task of Object.keys(ratings[cadence])) {
      if (ratings[cadence][task].verdict) n += 1;
    }
  }
  return n;
});
const totalTasks = computed(() => due.value.reduce((sum, b) => sum + b.tasks.length, 0));

const dockHint = computed(() => {
  if (!canSubmit) return t("access.needRound");
  if (totalRated.value >= totalTasks.value && totalTasks.value > 0) return t("round.due.allRated");
  return t("round.due.progress", { done: totalRated.value, total: totalTasks.value });
});

function clearRatings() {
  for (const k of Object.keys(ratings)) delete ratings[k];
}

function persistDraft() {
  writeRoundDraft(building.value, localDate(), ratings);
}

function restoreDraft() {
  const saved = readRoundDraft(building.value, localDate());
  if (!saved) return;
  for (const [cadence, tasks] of Object.entries(saved)) {
    if (tasks && typeof tasks === "object") ratings[cadence] = { ...tasks };
  }
}

function setRating(cadence, taskName, patch) {
  if (!ratings[cadence]) ratings[cadence] = {};
  const current = ratings[cadence][taskName] || { verdict: "", notes: "", photo: "" };
  ratings[cadence][taskName] = { ...current, ...patch };
  persistDraft();
}

function onRate(cadence, taskName, verdict) {
  setRating(cadence, taskName, { verdict });
}
function onNote(cadence, taskName, notes) {
  setRating(cadence, taskName, { notes });
}
function onPhoto(cadence, taskName, photo) {
  setRating(cadence, taskName, { photo });
}

function buildResults() {
  const out = [];
  for (const block of due.value) {
    const marks = ratings[block.cadence];
    if (!marks) continue;
    for (const task of block.tasks) {
      const mark = marks[task.name];
      if (!mark || !mark.verdict) continue;
      out.push({
        task: task.name,
        cadence: block.cadence,
        execution_status: STATUS[mark.verdict],
        notes: mark.notes || "",
        evidence_photo: mark.photo || "",
      });
    }
  }
  return out;
}

async function doSubmit() {
  submitError.value = "";
  const results = buildResults();
  if (!results.length) {
    submitError.value = t("round.submit.needOne");
    return;
  }
  try {
    const res = await submitRes.submit({
      building: building.value,
      round_date: localDate(),
      results: JSON.stringify(results),
    });
    const answer = res || submitRes.data || {};
    if (!answer.rounds || !answer.rounds.length) {
      const first = (answer.failed || [])[0];
      submitError.value = first ? first.message : t("errors.roundSubmitFailed");
      return;
    }
    submitted.value = answer;
    if (!answer.failed || !answer.failed.length) dropRoundDraft(building.value, localDate());
  } catch (e) {
    submitError.value = apiErrorMessage(e, "errors.roundSubmitFailed");
  }
}

/* A partial failure KEEPS the draft on purpose six lines above, so the walker can retry the
   cadences the server refused. Dropping it here destroyed exactly that — the only button on
   the success screen threw away the work it was preserved for. */
function resetAll() {
  const partial = !!(submitted.value && (submitted.value.failed || []).length);
  submitted.value = null;
  submitError.value = "";
  staleOffer.value = false;
  if (!partial) {
    dropRoundDraft(building.value, localDate());
    clearRatings();
  }
  if (building.value) dueRes.fetch();
}

function changeBuilding() {
  clearBuilding();
}

function load() {
  submitted.value = null;
  submitError.value = "";
  staleOffer.value = false;
  clearRatings();
  if (!building.value) return;
  restoreDraft();
  dueRes.fetch();
}

/* Every path that reads the round goes through the same building guard. Retry and the
   stale-data offer used to fetch unconditionally, so a reader with no building chosen
   asked the server for the rounds of nothing and was shown a failure for it. */
function acceptStale() {
  staleOffer.value = false;
  if (building.value) dueRes.fetch();
}

function resultTheme(value) {
  if (value === "Fail") return "red";
  if (value === "Needs Attention") return "orange";
  return "green";
}

let stopRealtime = () => {};

onMounted(() => {
  load();
  stopRealtime = connectSafetyRealtime(() => {
    if (building.value) staleOffer.value = true;
  });
});

onUnmounted(() => {
  stopRealtime();
});

watch(building, load);
</script>

<style scoped>
.due-intro {
  padding-inline: var(--sp-1);
}
.draft-note {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  margin-top: var(--sp-2);
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  color: var(--c-success);
}
.stale {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3);
  border-block: var(--border-width) solid var(--c-warning);
  border-inline-start: 3px solid var(--c-warning);
  background: var(--c-warning-bg);
}
.stale-title {
  font-weight: var(--fw-heading);
  color: var(--c-warning);
}
.stale-actions {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.stale-actions :deep(button) {
  min-block-size: var(--tap-min);
}

.done {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--sp-3);
  text-align: center;
}
.done-mark {
  display: grid;
  place-items: center;
  height: 72px;
  width: 72px;
  margin: var(--sp-3) auto 0;
  border-radius: var(--radius-pill);
  color: var(--c-primary-ink);
  background: var(--c-success);
}
.results {
  text-align: start;
  margin-top: var(--sp-3);
}
.results-head {
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
}
.result-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-1);
  border-block-end: var(--border-width) solid var(--c-border);
  background: transparent;
}
.result-failed {
  border-inline-start: 3px solid var(--c-danger);
  background: var(--c-danger-bg);
}
.result-cadence {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
}
.result-reason {
  font-size: var(--fs-sm);
  color: var(--c-danger);
  text-align: end;
}
.wide {
  inline-size: 100%;
}
.dock-error {
  margin-bottom: var(--sp-2);
}
.dock-hint {
  margin-top: var(--sp-2);
  text-align: center;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
</style>
