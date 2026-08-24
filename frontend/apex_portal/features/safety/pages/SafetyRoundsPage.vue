<script setup>
import { computed, inject, onBeforeUnmount, reactive, ref, watch } from "vue";
import { Button, ErrorMessage, Progress, createResource, toast } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import BuildingPicker from "../../housing/components/BuildingPicker.vue";
import { building } from "../../housing/building.js";
import SafetyTaskRow from "../components/SafetyTaskRow.vue";
import { cadenceLabel, periodLabel } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

const error = ref("");
const results = reactive({});
const due = createResource({
  url: "apex.habitat.api.safety_checklist.get_due_cadences",
  makeParams: () => ({ building: building.value }),
});
const submit = createResource({ url: "apex.habitat.api.safety_checklist.submit_due_rounds" });
const groups = computed(() => due.data?.due || []);
const awaiting = computed(() => due.data?.awaiting || []);
const taskCount = computed(() => groups.value.reduce((total, group) => total + group.tasks.length, 0));
const checkedCount = computed(() => Object.values(results).filter((row) => row.execution_status).length);
const checkedPercent = computed(() => taskCount.value
  ? Math.round((checkedCount.value / taskCount.value) * 100)
  : 0);
const missingEvidence = computed(() => groups.value.some((group) => group.tasks.some((task) => {
  const row = results[`${group.cadence}:${task.name}`];
  return Boolean(task.evidence_required)
    && ["Poor", "Not Done"].includes(row?.execution_status)
    && !row.evidence_photo;
})));
const checklistComplete = computed(() => taskCount.value > 0
  && checkedCount.value === taskCount.value
  && !missingEvidence.value);
// Save greys on two different unmet conditions and the progress bar named only one of them; an
// unanswered task read as the neutral word "تقدم الجولة" beside a dead button. Counting the
// remaining tasks says which ones, not merely that some are left.
const saveReason = computed(() => {
  if (missingEvidence.value) return __("Complete the required photos before saving the round.");
  if (!taskCount.value) return __("No items in this round.");
  const remaining = taskCount.value - checkedCount.value;
  if (remaining > 0) return __("{0} of {1} items left undecided.", [remaining, taskCount.value]);
  return "";
});
const progressLabel = computed(() => saveReason.value
  || (checklistComplete.value ? __("The round items are complete.") : __("Round Progress")));

const subscribeBuilding = inject("portalBuildingSubscribe", () => () => {});
let unsubscribers = [];
let liveBuilding = null;

function stopLive() {
  liveBuilding = null;
  while (unsubscribers.length) unsubscribers.pop()();
}

function startLive(name) {
  if (name === liveBuilding) return;
  liveBuilding = name;
  while (unsubscribers.length) unsubscribers.pop()();
  if (name) unsubscribers.push(subscribeBuilding(name, "doc_update", () => due.fetch()) || (() => {}));
}

watch(building, async (value) => {
  Object.keys(results).forEach((key) => delete results[key]);
  startLive(value);
  if (value) await due.fetch();
}, { immediate: true });
onBeforeUnmount(stopLive);
function update(task, cadence, value) {
  results[`${cadence}:${task}`] = { ...value, task, cadence };
}
function today() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Riyadh",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
async function saveRound() {
  error.value = "";
  if (!checklistComplete.value) {
    error.value = missingEvidence.value
      ? __("Complete the required photos before saving the round.")
      : __("Complete checking all items before saving the round.");
    return;
  }
  try {
    const response = await submit.submit({
      building: building.value,
      round_date: today(),
      results: JSON.stringify(Object.values(results)),
    });
    if (!response?.ok) throw new Error(response?.failed?.[0]?.message || __("The round was not saved."));
    // ok is true as long as ONE cadence was recorded, so a partial refusal has to be
    // named here or the supervisor walks away believing the whole round was saved.
    const failed = response.failed || [];
    if (failed.length) {
      const names = failed.map((row) => cadenceLabel(row.cadence)).join("، ");
      error.value = __("Partial save. Not saved: {0}. Review it and resubmit.", [names]);
    } else {
      toast.create({
        type: "success",
        message: response.ratified ? __("The round was approved") : __("The round was saved and is awaiting review"),
      });
    }
    Object.keys(results).forEach((key) => delete results[key]);
    await due.fetch();
  } catch (exception) {
    error.value = safeErrorMessage(exception, __("Could not save the round."));
  }
}
</script>

<template>
  <section class="feature-page safety-rounds-page">
    <header class="feature-page__header"><h2>{{ __("Safety Rounds") }}</h2><BuildingPicker /></header>
    <PortalSkeleton v-if="due.loading" :rows="3" :label="__('Loading Safety Rounds')" />
    <ErrorMessage v-else-if="due.error" :message="__('Could not load the safety rounds.')" />
    <template v-else-if="building">
      <section v-if="awaiting.length" class="feature-card">
        <h3>{{ __("Rounds Awaiting Review") }}</h3>
        <RouterLink v-for="item in awaiting" :key="item.round" :to="`/rounds/${item.round}`">
          {{ cadenceLabel(item.cadence) }} · {{ item.round_date }}
        </RouterLink>
      </section>
      <p v-if="!groups.length" class="feature-page__empty">{{ __("No due rounds for this building.") }}</p>
      <section v-for="group in groups" :key="group.cadence" class="safety-group">
        <h3>{{ cadenceLabel(group.cadence) }} · {{ periodLabel(group.period) }}</h3>
        <SafetyTaskRow
          v-for="task in group.tasks"
          :key="task.name"
          :task="task"
          :cadence="group.cadence"
          @change="update(task.name, group.cadence, $event)"
        />
      </section>
      <ErrorMessage v-if="error" :message="error" />
      <Progress
        v-if="groups.length"
        class="safety-checklist__progress"
        :value="checkedPercent"
        :label="progressLabel"
        size="lg"
        hint
      >
        <template #hint>{{ checkedCount }} {{ __("of") }} {{ taskCount }}</template>
      </Progress>
      <p v-if="groups.length && saveReason" class="feature-reason">{{ saveReason }}</p>
      <Button
        v-if="groups.length"
        class="safety-checklist__save"
        variant="solid"
        :disabled="!checklistComplete"
        :loading="submit.loading"
        @click="saveRound"
      >{{ __("Save Round") }}</Button>
    </template>
  </section>
</template>
