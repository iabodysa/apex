<template>
  <div class="app-shell" :dir="dir">
    <!-- Header: dark forest bar with the brand arc supergraphic. -->
    <header class="app-header">
      <div class="hero-arc" aria-hidden="true">
        <svg viewBox="0 0 200 200" fill="none" preserveAspectRatio="xMidYMid meet">
          <path d="M70 10 A95 95 0 0 1 70 190" stroke="currentColor" stroke-width="26" stroke-linecap="round" fill="none" />
          <path d="M120 35 A70 70 0 0 1 120 165" stroke="currentColor" stroke-width="26" stroke-linecap="round" fill="none" opacity="0.6" />
        </svg>
      </div>
      <div class="header-inner">
        <div class="header-bar">
          <div class="header-brand">
            <span class="header-mark"><Icon name="shield-check" :size="20" /></span>
            <span class="header-word">{{ t("common.appName") }}</span>
          </div>
          <LangToggle variant="header" />
        </div>
        <div class="greeting-block">
          <p class="greeting-eyebrow">{{ t("greeting.eyebrow") }}</p>
          <h1 class="greeting-title">{{ greeting }}</h1>
          <button v-if="building" type="button" class="building-chip" @click="changeBuilding">
            <Icon name="building" :size="14" />
            <span class="building-chip-name">{{ buildingLabel }}</span>
            <span class="building-chip-change">{{ t("common.change") }}</span>
          </button>
        </div>
      </div>
    </header>

    <main class="app-main">
      <!-- 1. No building chosen yet -> picker. -->
      <BuildingPicker v-if="!building" @select="onBuildingSelected" />

      <!-- 2. Building chosen: load / show due cadences. -->
      <template v-else>
        <!-- Loading the due set. -->
        <div v-if="dueRes.loading" class="state-center">
          <div class="spinner mx-auto"></div>
          <p class="state-msg">{{ t("common.loading") }}</p>
        </div>

        <!-- Error + retry. -->
        <div v-else-if="dueRes.error" class="state-center">
          <div class="state-icon state-icon-danger"><Icon name="triangle-alert" :size="24" /></div>
          <p class="state-title">{{ t("errors.loadFailed") }}</p>
          <p class="state-msg">{{ dueErrorMessage }}</p>
          <button class="btn btn-primary state-btn" @click="dueRes.reload()">{{ t("common.retry") }}</button>
        </div>

        <!-- Success state after a submit. -->
        <Transition name="swap" mode="out-in">
          <div v-if="submitted" key="done" class="success">
            <div class="success-burst">
              <div class="success-ring"></div>
              <div class="success-check"><Icon name="check" :size="40" /></div>
            </div>
            <h2 class="success-title">{{ t("success.title") }}</h2>
            <p class="success-sub">{{ t("success.subtitle") }}</p>

            <div class="emailed" :class="submitted.emailed ? 'emailed-ok' : 'emailed-warn'">
              <Icon name="mail" :size="16" />
              <span>{{ submitted.emailed ? t("success.emailed") : t("success.notEmailed") }}</span>
            </div>

            <div v-if="submitted.rounds && submitted.rounds.length" class="results">
              <p class="results-head">{{ t("success.results") }}</p>
              <div
                v-for="r in submitted.rounds"
                :key="r.cadence + r.safety_round"
                class="result-row"
                :class="resultClass(r.overall_result)"
              >
                <span class="result-cadence">{{ tEnum("cadence", r.cadence) }}</span>
                <span class="result-badge">
                  <Icon :name="resultIcon(r.overall_result)" :size="15" />
                  {{ tEnum("result", r.overall_result) }}
                </span>
              </div>
            </div>

            <button class="btn btn-outline success-again" @click="resetAll">
              {{ t("success.another") }}
            </button>
          </div>

          <!-- Empty: nothing due. -->
          <div v-else-if="due.length === 0" key="empty" class="empty">
            <div class="empty-burst">
              <div class="empty-ring"></div>
              <Icon name="shield-check" :size="44" />
            </div>
            <h2 class="empty-title">{{ t("empty.title") }}</h2>
            <p class="empty-sub">{{ t("empty.subtitle") }}</p>
            <button class="btn btn-outline empty-switch" @click="changeBuilding">
              {{ t("empty.switch") }}
            </button>
          </div>

          <!-- Due rounds: the working checklist. -->
          <div v-else key="due" class="due">
            <div class="due-intro">
              <h2 class="section-title">{{ t("due.title") }}</h2>
              <p class="due-sub">{{ t("due.subtitle") }}</p>
            </div>

            <CadenceSection
              v-for="block in due"
              :key="block.cadence"
              :block="block"
              :ratings="ratings[block.cadence] || {}"
              @rate="onRate"
              @note="onNote"
            />

            <p v-if="submitError" class="status-note status-err">{{ submitError }}</p>

            <div class="submit-dock">
              <p class="submit-progress">
                <span class="submit-dot" :class="{ 'submit-dot-ready': totalRated > 0 }"></span>
                {{ progressLabel }}
              </p>
              <button
                class="btn btn-primary submit-btn"
                :disabled="totalRated === 0 || submitRes.loading"
                @click="doSubmit"
              >
                <template v-if="submitRes.loading">
                  <span class="btn-spin"><Icon name="loader" :size="18" /></span>
                  {{ t("submit.sending") }}
                </template>
                <template v-else>
                  <Icon name="send" :size="18" />
                  {{ t("submit.cta") }}
                </template>
              </button>
              <p class="submit-hint">{{ t("submit.hint") }}</p>
            </div>
          </div>
        </Transition>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { createResource } from "frappe-ui";
import Icon from "./components/Icon.vue";
import LangToggle from "./components/LangToggle.vue";
import BuildingPicker from "./components/BuildingPicker.vue";
import CadenceSection from "./components/CadenceSection.vue";
import { useI18n, resourceErrorMessage } from "./i18n";

const { t, tEnum, dir } = useI18n();

// Keep the document direction/lang in sync with the toggle.
watch(
  dir,
  (d) => {
    document.documentElement.setAttribute("dir", d);
    document.documentElement.setAttribute("lang", d === "rtl" ? "ar" : "en");
  },
  { immediate: true },
);

// ---- selected building -------------------------------------------------
const building = ref("");
const buildingLabel = ref("");
const submitted = ref(null);
const submitError = ref("");

// ratings: { [cadence]: { [taskName]: { verdict, notes } } }
const ratings = reactive({});

// ---- due cadences resource (the contract's get_due_cadences) -----------
const dueRes = createResource({
  url: "apex_habitat.habitat.api.safety_checklist.get_due_cadences",
  makeParams: () => ({ building: building.value }),
});

const due = computed(() => (dueRes.data && dueRes.data.due) || []);
const dueErrorMessage = computed(() => resourceErrorMessage(dueRes.error, "errors.loadFailed"));

// ---- submit resource (the contract's submit_due_rounds) ----------------
const submitRes = createResource({
  url: "apex_habitat.habitat.api.safety_checklist.submit_due_rounds",
});

// Verdict -> execution_status, mirroring TaskRow's mapping owner:
//   pass -> Good   fail -> Not Done   issue -> Poor
const STATUS = { pass: "Good", fail: "Not Done", issue: "Poor" };

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
const progressLabel = computed(() =>
  totalRated.value >= totalTasks.value && totalTasks.value > 0
    ? t("due.allRated")
    : t("due.progress", { done: totalRated.value, total: totalTasks.value }),
);

const today = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

// ---- flow handlers -----------------------------------------------------
function onBuildingSelected(name, label) {
  building.value = name;
  buildingLabel.value = label || name;
  submitted.value = null;
  submitError.value = "";
  for (const k of Object.keys(ratings)) delete ratings[k];
  dueRes.fetch();
}

function changeBuilding() {
  building.value = "";
  buildingLabel.value = "";
  submitted.value = null;
  submitError.value = "";
  for (const k of Object.keys(ratings)) delete ratings[k];
}

function resetAll() {
  // After a submit, re-fetch the same building so it reflects what is now closed.
  const b = building.value;
  submitted.value = null;
  submitError.value = "";
  for (const k of Object.keys(ratings)) delete ratings[k];
  if (b) dueRes.fetch();
}

function onRate(cadence, taskName, verdict) {
  if (!ratings[cadence]) ratings[cadence] = {};
  const cur = ratings[cadence][taskName] || { verdict: "", notes: "" };
  ratings[cadence][taskName] = { ...cur, verdict };
}

function onNote(cadence, taskName, notes) {
  if (!ratings[cadence]) ratings[cadence] = {};
  const cur = ratings[cadence][taskName] || { verdict: "", notes: "" };
  ratings[cadence][taskName] = { ...cur, notes };
}

function buildResults() {
  const out = [];
  for (const cadence of Object.keys(ratings)) {
    for (const task of Object.keys(ratings[cadence])) {
      const r = ratings[cadence][task];
      if (!r.verdict) continue; // unrated tasks are not submitted
      out.push({
        task,
        cadence,
        execution_status: STATUS[r.verdict],
        notes: r.notes || "",
      });
    }
  }
  return out;
}

async function doSubmit() {
  submitError.value = "";
  const results = buildResults();
  if (!results.length) {
    submitError.value = t("submit.needOne");
    return;
  }
  // createResource.submit() swallows failures into submitRes.error rather than
  // re-throwing, so we branch on the resource's own error/data after awaiting —
  // a try/catch here would never fire and could show success on a failed POST.
  const res = await submitRes.submit({
    building: building.value,
    round_date: today(),
    results: JSON.stringify(results),
  });
  if (submitRes.error) {
    submitError.value = resourceErrorMessage(submitRes.error, "errors.submitFailed");
    return;
  }
  submitted.value = res || submitRes.data || { ok: true, rounds: [], emailed: false };
}

// ---- greeting + result styling -----------------------------------------
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 12) return t("greeting.morning");
  if (h < 18) return t("greeting.afternoon");
  return t("greeting.evening");
});

function resultClass(r) {
  if (r === "Fail") return "result-fail";
  if (r === "Needs Attention") return "result-warn";
  return "result-pass";
}
function resultIcon(r) {
  if (r === "Fail") return "x";
  if (r === "Needs Attention") return "triangle-alert";
  return "check";
}
</script>

<style scoped>
.app-main {
  flex: 1;
  padding: 18px 16px 40px;
}

/* ---- header ---------------------------------------------------------- */
.header-inner {
  position: relative;
  z-index: 1;
  padding: 16px 16px 20px;
}
.header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.header-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.header-mark {
  display: grid;
  place-items: center;
  height: 32px;
  width: 32px;
  border-radius: var(--radius);
  color: var(--c-header-bg);
  background: var(--c-header-accent);
  flex-shrink: 0;
}
.header-word {
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  letter-spacing: -0.01em;
  color: var(--c-header-ink);
}
.greeting-block {
  margin-top: 14px;
}
.greeting-eyebrow {
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--c-header-accent);
}
.greeting-title {
  font-size: var(--fs-h1);
  font-weight: var(--fw-heading);
  line-height: 1.15;
  color: var(--c-header-ink);
  margin-top: 2px;
}
.building-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-top: 12px;
  padding: 7px 7px 7px 12px;
  border-radius: var(--radius-pill);
  border: none;
  cursor: pointer;
  background: color-mix(in srgb, var(--c-header-ink) 14%, transparent);
  color: var(--c-header-ink);
  max-width: 100%;
}
.building-chip-name {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.building-chip-change {
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  background: var(--c-header-accent);
  color: var(--c-header-bg);
  flex-shrink: 0;
}

/* ---- generic states -------------------------------------------------- */
.state-center {
  text-align: center;
  padding: 40px 16px;
}
.state-icon {
  display: grid;
  place-items: center;
  height: 52px;
  width: 52px;
  margin: 0 auto 14px;
  border-radius: var(--radius-lg);
}
.state-icon-danger {
  color: var(--c-danger);
  background: var(--c-danger-bg);
}
.state-title {
  font-weight: var(--fw-heading);
  font-size: var(--fs-h3);
  color: var(--c-ink);
}
.state-msg {
  margin-top: 6px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.state-btn {
  width: auto;
  padding-inline: 28px;
  margin: 16px auto 0;
}

/* ---- due list -------------------------------------------------------- */
.due {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.due-intro {
  padding: 0 2px;
}
.due-sub {
  margin-top: 4px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}

/* ---- submit dock ----------------------------------------------------- */
.submit-dock {
  margin-top: 4px;
  text-align: center;
}
.submit-progress {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-ink-soft);
  margin-bottom: 12px;
}
.submit-dot {
  height: 9px;
  width: 9px;
  border-radius: 999px;
  background: var(--c-muted);
  transition: background 0.25s ease;
}
.submit-dot-ready {
  background: var(--c-success);
  box-shadow: 0 0 0 4px var(--c-success-bg);
}
.submit-btn {
  box-shadow: 0 6px 20px color-mix(in srgb, var(--c-primary) 28%, transparent);
}
.btn-spin {
  display: inline-grid;
  place-items: center;
  animation: spin 0.7s linear infinite;
}
.submit-hint {
  margin-top: 10px;
  font-size: var(--fs-xs);
  color: var(--c-muted);
}

/* ---- success --------------------------------------------------------- */
.success,
.empty {
  text-align: center;
  padding: 16px 8px 8px;
}
.success-burst {
  position: relative;
  height: 96px;
  width: 96px;
  margin: 8px auto 18px;
  display: grid;
  place-items: center;
}
.success-ring {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: var(--c-success-bg);
  animation: pop 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}
.success-check {
  position: relative;
  display: grid;
  place-items: center;
  height: 64px;
  width: 64px;
  border-radius: 999px;
  color: var(--c-primary-ink);
  background: var(--c-success);
  animation: pop 0.45s 0.08s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.success-title {
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
}
.success-sub {
  margin-top: 6px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.emailed {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-top: 16px;
  padding: 9px 16px;
  border-radius: var(--radius-pill);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
}
.emailed-ok {
  color: var(--c-success);
  background: var(--c-success-bg);
}
.emailed-warn {
  color: var(--c-warning);
  background: var(--c-warning-bg);
}
.results {
  margin-top: 22px;
  text-align: start;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.results-head {
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--c-muted);
  margin-bottom: 2px;
}
.result-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--c-border);
  background: var(--c-surface);
}
.result-cadence {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
}
.result-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-sm);
  font-weight: var(--fw-heading);
  padding: 5px 11px;
  border-radius: var(--radius-pill);
}
.result-pass .result-badge {
  color: var(--c-success);
  background: var(--c-success-bg);
}
.result-warn .result-badge {
  color: var(--c-warning);
  background: var(--c-warning-bg);
}
.result-fail .result-badge {
  color: var(--c-danger);
  background: var(--c-danger-bg);
}
.success-again,
.empty-switch {
  width: auto;
  padding-inline: 26px;
  margin: 26px auto 0;
}

/* ---- empty ----------------------------------------------------------- */
.empty {
  padding-top: 40px;
}
.empty-burst {
  position: relative;
  display: grid;
  place-items: center;
  height: 104px;
  width: 104px;
  margin: 0 auto 20px;
  color: var(--c-primary);
}
.empty-ring {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
}
.empty-title {
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.2;
}
.empty-sub {
  margin-top: 8px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
  max-width: 280px;
  margin-inline: auto;
}

/* ---- transitions ----------------------------------------------------- */
.swap-enter-active,
.swap-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.25s ease;
}
.swap-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.swap-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@keyframes pop {
  from {
    opacity: 0;
    transform: scale(0.4);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
