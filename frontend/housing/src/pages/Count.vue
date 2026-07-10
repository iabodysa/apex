<!-- Copyright (c) 2026, AFMCO and contributors -->
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
          <div v-if="showBrand" class="header-brand">
            <img v-if="brandLogo" :src="brandLogo" alt="AFMCO" class="header-logo" />
            <template v-else>
              <span class="header-mark"><Icon name="package" :size="20" /></span>
              <span class="header-word">{{ t("common.appName") }}</span>
            </template>
          </div>
          <span v-else class="header-word">{{ t("common.appName") }}</span>
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

      <template v-else>
        <!-- Loading the inventory. -->
        <div v-if="invRes.loading" class="state-center">
          <div class="spinner mx-auto"></div>
          <p class="state-msg">{{ t("common.loading") }}</p>
        </div>

        <!-- Error + retry. -->
        <div v-else-if="invRes.error" class="state-center">
          <div class="state-icon state-icon-danger"><Icon name="triangle-alert" :size="24" /></div>
          <p class="state-title">{{ t("errors.loadFailed") }}</p>
          <p class="state-msg">{{ invErrorMessage }}</p>
          <button class="btn btn-primary state-btn" @click="invRes.reload()">{{ t("common.retry") }}</button>
        </div>

        <Transition name="swap" mode="out-in">
          <!-- Success: the count summary. -->
          <div v-if="submitted" key="done" class="success">
            <div class="success-burst">
              <div class="success-ring"></div>
              <div class="success-check"><Icon name="check" :size="40" /></div>
            </div>
            <h2 class="success-title">{{ t("success.title") }}</h2>
            <p class="success-sub">{{ t("success.subtitle") }}</p>

            <div class="emailed" :class="submitted.failed ? 'emailed-warn' : 'emailed-ok'">
              <Icon name="clipboard-check" :size="16" />
              <span v-if="submitted.failed">{{ t("success.partial", { ok: submitted.saved, failed: submitted.failed }) }}</span>
              <span v-else>{{ t("success.saved", { n: submitted.saved }) }}</span>
            </div>

            <div v-if="summaryRows.length" class="results">
              <p class="results-head">{{ t("success.results") }}</p>
              <div
                v-for="r in summaryRows"
                :key="r.name"
                class="summary-row"
                :class="varianceRowClass(r.quantity_variance)"
              >
                <span class="summary-name">{{ r.item_name }}</span>
                <span class="summary-badge">
                  <Icon :name="varianceIcon(r.quantity_variance)" :size="14" />
                  {{ varianceBadge(r.quantity_variance) }}
                </span>
              </div>
            </div>

            <button class="btn btn-outline success-again" @click="resetAll">
              {{ t("success.another") }}
            </button>
          </div>

          <!-- Empty: nothing to count. -->
          <div v-else-if="rows.length === 0" key="empty" class="empty">
            <div class="empty-burst">
              <div class="empty-ring"></div>
              <Icon name="package" :size="44" />
            </div>
            <h2 class="empty-title">{{ t("empty.title") }}</h2>
            <p class="empty-sub">{{ t("empty.subtitle") }}</p>
            <button class="btn btn-outline empty-switch" @click="changeBuilding">
              {{ t("empty.switch") }}
            </button>
          </div>

          <!-- Inventory list grouped by room. -->
          <div v-else key="list" class="list">
            <div class="list-intro">
              <h2 class="section-title">{{ t("list.title") }}</h2>
              <p class="list-sub">{{ t("list.subtitle") }}</p>
            </div>

            <!-- Needs-count / variance filter. -->
            <div class="filter-bar" role="group">
              <button
                type="button"
                class="filter-opt"
                :class="{ 'filter-opt-active': filter === 'all' }"
                @click="filter = 'all'"
              >
                {{ t("list.filterAll") }}
              </button>
              <button
                type="button"
                class="filter-opt"
                :class="{ 'filter-opt-active': filter === 'needs' }"
                @click="filter = 'needs'"
              >
                <Icon name="filter" :size="14" />
                {{ t("list.filterNeedsCount") }}
              </button>
            </div>

            <div v-if="!filteredGroups.length" class="state-center">
              <p class="state-msg">{{ t("list.empty") }}</p>
            </div>

            <section v-for="g in filteredGroups" :key="g.key" class="room-group">
              <header class="room-head">
                <span class="room-mark"><Icon name="door" :size="16" /></span>
                <span class="room-name">{{ g.label }}</span>
                <span class="room-count">{{ t("list.count", { n: g.items.length }) }}</span>
              </header>
              <div class="room-items">
                <ItemCountCard
                  v-for="item in g.items"
                  :key="item.name"
                  :row="item"
                  :model="staged[item.name] || baseModel(item)"
                  :conditions="conditions"
                  :staged="!!touched[item.name]"
                  @count="(v) => onCount(item, v)"
                  @condition="(v) => onCondition(item, v)"
                  @note="(v) => onNote(item, v)"
                />
              </div>
            </section>

            <p v-if="submitError" class="status-note status-err">{{ submitError }}</p>

            <div class="submit-dock">
              <p class="submit-progress">
                <span class="submit-dot" :class="{ 'submit-dot-ready': touchedCount > 0 }"></span>
                {{ progressLabel }}
              </p>
              <button
                class="btn btn-primary submit-btn"
                :disabled="touchedCount === 0 || submitRes.loading"
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
import Icon from "../components/Icon.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import BuildingPicker from "@shared/components/BuildingPicker.vue";
import ItemCountCard from "../components/ItemCountCard.vue";
import { useI18n, resourceErrorMessage } from "../i18n";

const { t, dir } = useI18n();

// Branding flags projected by the page template (www/housing-count.html).
const showBrand = computed(() => window.portal_show_brand !== false);
const brandLogo = computed(() => window.portal_logo || "");

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
const filter = ref("all");

// staged[name] = { counted_quantity, condition, notes }; touched[name] = true.
const staged = reactive({});
const touched = reactive({});

// ---- inventory resource ------------------------------------------------
const invRes = createResource({
  url: "apex.habitat.api.housing_count.get_inventory_for_building",
  makeParams: () => ({ building: building.value }),
});

const rows = computed(() => (invRes.data && invRes.data.items) || []);
const conditions = computed(() => (invRes.data && invRes.data.conditions) || []);
const invErrorMessage = computed(() => resourceErrorMessage(invRes.error, "errors.loadFailed"));

// ---- submit resource ---------------------------------------------------
const submitRes = createResource({
  url: "apex.habitat.api.housing_count.submit_counts",
});

function baseModel(item) {
  return {
    counted_quantity: Number(item.counted_quantity || 0),
    condition: item.condition || "Good",
    notes: item.notes || "",
  };
}

// "Needs count / variance": never counted (no last_count_date) OR a non-zero
// server variance. The variance is the server figure, never recomputed here.
function needsCount(item) {
  if (!item.last_count_date) return true;
  return Number(item.quantity_variance || 0) !== 0;
}

// Group rows by room for the room-banded list; a room-less item falls into a
// "no specific room" bucket sorted last.
const grouped = computed(() => {
  const map = new Map();
  for (const item of rows.value) {
    const key = item.room || "__none__";
    if (!map.has(key)) {
      map.set(key, {
        key,
        label: item.room_label || item.room || t("list.noRoom"),
        items: [],
      });
    }
    map.get(key).items.push(item);
  }
  return [...map.values()].sort((a, b) => {
    if (a.key === "__none__") return 1;
    if (b.key === "__none__") return -1;
    return String(a.label).localeCompare(String(b.label));
  });
});

const filteredGroups = computed(() => {
  if (filter.value !== "needs") return grouped.value;
  return grouped.value
    .map((g) => ({ ...g, items: g.items.filter(needsCount) }))
    .filter((g) => g.items.length);
});

const touchedCount = computed(() => Object.keys(touched).length);
const progressLabel = computed(() => t("list.count", { n: touchedCount.value }));

// ---- flow handlers -----------------------------------------------------
function onBuildingSelected(name, label) {
  building.value = name;
  buildingLabel.value = label || name;
  submitted.value = null;
  submitError.value = "";
  filter.value = "all";
  clearStaged();
  invRes.fetch();
}

function changeBuilding() {
  building.value = "";
  buildingLabel.value = "";
  submitted.value = null;
  submitError.value = "";
  clearStaged();
}

function resetAll() {
  const b = building.value;
  submitted.value = null;
  submitError.value = "";
  clearStaged();
  if (b) invRes.fetch();
}

function clearStaged() {
  for (const k of Object.keys(staged)) delete staged[k];
  for (const k of Object.keys(touched)) delete touched[k];
}

function ensure(item) {
  if (!staged[item.name]) staged[item.name] = baseModel(item);
  touched[item.name] = true;
  return staged[item.name];
}

function onCount(item, value) {
  ensure(item).counted_quantity = value;
}
function onCondition(item, value) {
  ensure(item).condition = value;
}
function onNote(item, value) {
  ensure(item).notes = value;
}

function buildLines() {
  const out = [];
  for (const name of Object.keys(touched)) {
    const m = staged[name];
    if (!m) continue;
    out.push({
      name,
      counted_quantity: m.counted_quantity,
      condition: m.condition,
      notes: m.notes || "",
    });
  }
  return out;
}

async function doSubmit() {
  submitError.value = "";
  const lines = buildLines();
  if (!lines.length) {
    submitError.value = t("submit.needOne");
    return;
  }
  const res = await submitRes.submit({
    building: building.value,
    lines: JSON.stringify(lines),
  });
  if (submitRes.error) {
    submitError.value = resourceErrorMessage(submitRes.error, "errors.submitFailed");
    return;
  }
  submitted.value = res || submitRes.data || { saved: 0, failed: 0, rows: [] };
}

// ---- success summary ---------------------------------------------------
const summaryRows = computed(() => (submitted.value && submitted.value.rows) || []);

function varianceRowClass(v) {
  const n = Number(v || 0);
  if (n < 0) return "summary-shortage";
  if (n > 0) return "summary-surplus";
  return "summary-balanced";
}
function varianceIcon(v) {
  const n = Number(v || 0);
  if (n < 0) return "triangle-alert";
  if (n > 0) return "scale";
  return "check";
}
function varianceBadge(v) {
  const n = Number(v || 0);
  const mag = Number.isInteger(n) ? Math.abs(n) : Math.abs(n).toFixed(2);
  if (n < 0) return t("success.shortage") + " " + mag;
  if (n > 0) return t("success.surplus") + " " + mag;
  return t("success.balanced");
}

// ---- greeting ----------------------------------------------------------
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 12) return t("greeting.morning");
  if (h < 18) return t("greeting.afternoon");
  return t("greeting.evening");
});
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
.header-logo {
  height: 28px;
  width: auto;
  max-width: 140px;
  object-fit: contain;
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
  padding: 32px 16px;
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

/* ---- list ------------------------------------------------------------ */
.list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.list-intro {
  padding: 0 2px;
}
.list-sub {
  margin-top: 4px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.filter-bar {
  display: flex;
  gap: 8px;
}
.filter-opt {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 14px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--c-border-strong);
  background: var(--c-surface);
  color: var(--c-ink-soft);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.filter-opt-active {
  background: var(--c-primary);
  color: var(--c-primary-ink);
  border-color: var(--c-primary);
}

.room-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: var(--radius);
  border: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-ink) 3%, transparent);
}
.room-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.room-mark {
  display: grid;
  place-items: center;
  height: 28px;
  width: 28px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  color: var(--c-ink-soft);
  background: color-mix(in srgb, var(--c-ink) 8%, transparent);
}
.room-name {
  flex: 1;
  font-size: var(--fs-body);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
}
.room-count {
  font-size: var(--fs-xs);
  color: var(--c-muted);
}
.room-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
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
.summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--c-border);
  background: var(--c-surface);
}
.summary-name {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.summary-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-sm);
  font-weight: var(--fw-heading);
  padding: 5px 11px;
  border-radius: var(--radius-pill);
  flex-shrink: 0;
}
.summary-balanced .summary-badge {
  color: var(--c-success);
  background: var(--c-success-bg);
}
.summary-surplus .summary-badge {
  color: var(--c-warning);
  background: var(--c-warning-bg);
}
.summary-shortage .summary-badge {
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

/* ---- tablet / iPad (≥768px) ----------------------------------------- */
@media (min-width: 768px) {
  .header-inner {
    padding: 24px 28px 28px;
  }
  .app-main {
    padding: 28px 28px 56px;
  }
  .greeting-title {
    font-size: var(--fs-display);
  }
  .list {
    gap: 18px;
  }
  .list-intro .section-title {
    font-size: var(--fs-h1);
  }
}
</style>
