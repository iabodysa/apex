<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button, ErrorMessage, LoadingIndicator, createResource, toast } from "frappe-ui";
import BuildingPicker from "../../housing/components/BuildingPicker.vue";
import { building } from "../../housing/building.js";
import SafetyTaskRow from "../components/SafetyTaskRow.vue";
import { cadenceLabel, periodLabel } from "../../../core/displayLabels.js";

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
const missingEvidence = computed(() => groups.value.some((group) => group.tasks.some((task) => {
  const row = results[`${group.cadence}:${task.name}`];
  return Boolean(task.evidence_required)
    && ["Poor", "Not Done"].includes(row?.execution_status)
    && !row.evidence_photo;
})));
const checklistComplete = computed(() => taskCount.value > 0
  && checkedCount.value === taskCount.value
  && !missingEvidence.value);
const progressLabel = computed(() => {
  if (missingEvidence.value) return "أكمل الصور المطلوبة قبل حفظ الجولة.";
  if (checklistComplete.value) return "اكتملت بنود الجولة.";
  return `${checkedCount.value} من ${taskCount.value} تم فحصها.`;
});

watch(building, async (value) => {
  Object.keys(results).forEach((key) => delete results[key]);
  if (value) await due.fetch();
});
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
      ? "أكمل الصور المطلوبة قبل حفظ الجولة."
      : "أكمل فحص جميع البنود قبل حفظ الجولة.";
    return;
  }
  try {
    const response = await submit.submit({
      building: building.value,
      round_date: today(),
      results: JSON.stringify(Object.values(results)),
    });
    if (!response?.ok) throw new Error(response?.failed?.[0]?.message || "لم تُحفظ الجولة.");
    toast.create({
      type: "success",
      message: response.ratified ? "تم اعتماد الجولة" : "حُفظت الجولة وتنتظر المراجعة",
    });
    Object.keys(results).forEach((key) => delete results[key]);
    await due.fetch();
  } catch (exception) {
    error.value = exception.message || "تعذر حفظ الجولة.";
  }
}
</script>

<template>
  <section class="feature-page">
    <header class="feature-page__header"><h2>جولات السلامة</h2><BuildingPicker /></header>
    <LoadingIndicator v-if="due.loading" aria-label="جارٍ تحميل الجولات" />
    <ErrorMessage v-else-if="due.error" message="تعذر تحميل جولات السلامة." />
    <template v-else-if="building">
      <section v-if="awaiting.length" class="feature-card">
        <h3>جولات تنتظر المراجعة</h3>
        <RouterLink v-for="item in awaiting" :key="item.round" :to="`/rounds/${item.round}`">
          {{ cadenceLabel(item.cadence) }} · {{ item.round_date }}
        </RouterLink>
      </section>
      <p v-if="!groups.length" class="feature-page__empty">لا توجد جولات مستحقة لهذا المبنى.</p>
      <section v-for="group in groups" :key="group.cadence" class="safety-group">
        <h3>{{ cadenceLabel(group.cadence) }} · {{ periodLabel(group.period) }}</h3>
        <SafetyTaskRow
          v-for="task in group.tasks"
          :key="task.name"
          :task="{ ...task, cadence: group.cadence }"
          @change="update(task.name, group.cadence, $event)"
        />
      </section>
      <ErrorMessage v-if="error" :message="error" />
      <p v-if="groups.length" class="safety-checklist__progress" role="status">{{ progressLabel }}</p>
      <Button
        v-if="groups.length"
        class="safety-checklist__save"
        variant="solid"
        :disabled="!checklistComplete"
        :loading="submit.loading"
        @click="saveRound"
      >حفظ الجولة</Button>
    </template>
  </section>
</template>
