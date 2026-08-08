<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <BuildingPicker v-if="!building" @select="onBuildingSelected" />

  <ListSkeleton v-else-if="invRes.loading && !rows.length" :rows="6" :label="t('list.loadingLabel')" />

  <LoadError
    v-else-if="invRes.error"
    :title="t('errors.loadFailed')"
    :detail="invErrorMessage"
    :hint="t('errors.retryHint')"
    :retry-label="t('common.retry')"
    @retry="invRes.reload()"
  />

  <EmptyState v-else-if="!rows.length" :title="t('empty.title')" :hint="t('empty.subtitle')">
    <template #icon><Icon name="package" :size="24" /></template>
    <template #action>
      <Button size="xl" variant="outline" :label="t('empty.switch')" @click="onChangeBuilding" />
    </template>
  </EmptyState>

  <template v-else>
    <div class="hz-split">
      <div class="hz-split-list">
        <TabButtons
          class="filter"
          v-model="filter"
          :dir="dir"
          :buttons="[
            { label: t('list.filterAll'), value: 'all' },
            { label: t('list.filterNeedsCount'), value: 'needs' },
          ]"
        />

        <p class="hint draft-note">
          <Icon name="shield" :size="13" /> {{ t("list.draftKept") }}
        </p>

        <EmptyState
          v-if="!filteredGroups.length"
          :title="t('list.filteredTitle')"
          :hint="t('list.filteredHint')"
        >
          <template #icon><Icon name="check-circle" :size="24" /></template>
          <template #action>
            <Button size="xl" variant="outline" :label="t('list.clearFilter')" @click="filter = 'all'" />
          </template>
        </EmptyState>

        <section v-for="g in filteredGroups" :key="g.key" class="room">
          <h2 class="room-head">
            <span class="room-mark"><Icon name="door" :size="16" /></span>
            <span class="room-name">{{ g.label }}</span>
            <span class="room-count">{{ t("list.count", { n: g.items.length }) }}</span>
          </h2>
          <CountItemRow
            v-for="item in g.items"
            :key="item.name"
            :row="item"
            :model="modelFor(item)"
            :edited="!!staged[item.name]"
            :open="selected === item.name"
            @open="openItem(item.name)"
          />
        </section>
      </div>

      <aside v-if="desktop" class="hz-split-detail">
        <div v-if="selectedRow" class="pane">
          <CountItemEditor
            :row="selectedRow"
            :model="modelFor(selectedRow)"
            :conditions="conditions"
            :room-label="roomLabelFor(selectedRow)"
            @count="(v) => onCount(selectedRow, v)"
            @condition="(v) => onCondition(selectedRow, v)"
            @note="(v) => onNote(selectedRow, v)"
          />
        </div>
        <div v-else class="pane pane-idle">
          <EmptyState :title="t('list.pickTitle')" :hint="t('list.pickHint')">
            <template #icon><Icon name="box" :size="24" /></template>
          </EmptyState>
        </div>
      </aside>
    </div>

    <div class="hz-dock">
      <ErrorMessage v-if="submitError" class="dock-error" :message="submitError" />
      <Button
        class="dock-btn"
        size="2xl"
        variant="solid"
        theme="green"
        :loading="submitRes.loading"
        :loading-text="t('submit.sending')"
        :disabled="touchedCount === 0 || !canCount"
        :label="t('submit.cta')"
        @click="doSubmit"
      >
        <template #prefix><Icon name="send" :size="20" /></template>
      </Button>
      <p class="dock-hint">
        {{ dockHint }}
      </p>
    </div>

    <Dialog
      v-if="!desktop"
      :modelValue="!!selectedRow"
      :options="{
        title: selectedRow ? t('card.title', { name: selectedRow.item_name }) : '',
        size: 'lg',
      }"
      @update:modelValue="(open) => !open && closeItem()"
    >
      <template #body-content>
        <CountItemEditor
          v-if="selectedRow"
          :row="selectedRow"
          :model="modelFor(selectedRow)"
          :conditions="conditions"
          :room-label="roomLabelFor(selectedRow)"
          :heading="false"
          @count="(v) => onCount(selectedRow, v)"
          @condition="(v) => onCondition(selectedRow, v)"
          @note="(v) => onNote(selectedRow, v)"
        />
      </template>
      <template #actions>
        <Button
          class="dock-btn"
          size="2xl"
          variant="solid"
          theme="green"
          :label="t('common.done')"
          @click="closeItem"
        />
      </template>
    </Dialog>
  </template>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button, Dialog, ErrorMessage, TabButtons, createResource, toast } from "frappe-ui";
import BuildingPicker from "@shared/components/BuildingPicker.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import CountItemRow from "../components/CountItemRow.vue";
import CountItemEditor from "../components/CountItemEditor.vue";
import ListSkeleton from "../components/ListSkeleton.vue";
import LoadError from "../components/LoadError.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { useDesktop } from "@shared/useBreakpoint.js";
import { can } from "../portal.js";
import { dropCountDraft, readCountDraft, writeCountDraft } from "../drafts.js";
import { building, clearBuilding, countProgress, selectBuilding } from "../session";

const { t, dir } = useI18n();
const route = useRoute();
const router = useRouter();
const desktop = useDesktop();

const submitError = ref("");
const canCount = can("count");

const staged = reactive({});

const invRes = createResource({
  url: "apex.habitat.api.housing_count.get_inventory_for_building",
  makeParams: () => ({ building: building.value }),
});

const submitRes = createResource({
  url: "apex.habitat.api.housing_count.submit_counts",
});

const rows = computed(() => (invRes.data && invRes.data.items) || []);
const conditions = computed(() => (invRes.data && invRes.data.conditions) || []);
const invErrorMessage = computed(() => resourceErrorMessage(invRes.error, "errors.loadFailed"));

const selected = computed(() => route.params.item || "");
const selectedRow = computed(() => rows.value.find((r) => r.name === selected.value) || null);

function openItem(name) {
  router.push({ path: "/count/" + encodeURIComponent(name), query: route.query });
}
function closeItem() {
  router.push({ path: "/count", query: route.query });
}

const filter = computed({
  get: () => (route.query.filter === "needs" ? "needs" : "all"),
  set: (value) => {
    const query = { ...route.query };
    if (value === "needs") query.filter = "needs";
    else delete query.filter;
    router.replace({ path: route.path, query });
  },
});

function baseModel(item) {
  return {
    counted_quantity: Number(item.counted_quantity || 0),
    condition: item.condition || "Good",
    notes: item.notes || "",
  };
}
function modelFor(item) {
  return staged[item.name] || baseModel(item);
}

function needsCount(item) {
  if (!item.last_count_date) return true;
  return Number(item.quantity_variance || 0) !== 0;
}

const grouped = computed(() => {
  const map = new Map();
  for (const item of rows.value) {
    const key = item.room || "__none__";
    if (!map.has(key)) {
      map.set(key, { key, label: item.room_label || item.room || t("list.noRoom"), items: [] });
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

function roomLabelFor(item) {
  return item.room_label || item.room || "";
}

const touchedCount = computed(() => Object.keys(staged).length);

const dockHint = computed(() => {
  if (!canCount) return t("access.hint");
  return touchedCount.value ? t("submit.ready", { n: touchedCount.value }) : t("submit.needOne");
});

watch(
  [touchedCount, rows],
  () => {
    countProgress.value = { done: touchedCount.value, total: rows.value.length };
  },
  { immediate: true },
);

function clearStaged() {
  for (const k of Object.keys(staged)) delete staged[k];
}

function persistDraft() {
  writeCountDraft(building.value, staged);
}

function restoreDraft() {
  const saved = readCountDraft(building.value);
  if (!saved) return 0;
  let restored = 0;
  for (const [name, model] of Object.entries(saved)) {
    if (!model || typeof model !== "object") continue;
    staged[name] = {
      counted_quantity: Number(model.counted_quantity || 0),
      condition: model.condition || "Good",
      notes: model.notes || "",
    };
    restored += 1;
  }
  return restored;
}

function announceRestored(restored) {
  if (restored) toast.create({ type: "info", message: t("list.draftRestored", { n: restored }) });
}

function onBuildingSelected(name, label) {
  selectBuilding(name, label);
}

function onChangeBuilding() {
  clearBuilding();
  router.push("/count");
}

watch(building, (name) => {
  clearStaged();
  submitError.value = "";
  if (!name) return;
  announceRestored(restoreDraft());
  invRes.fetch();
});

onMounted(() => {
  if (!building.value) return;
  announceRestored(restoreDraft());
  invRes.fetch();
});

function ensure(item) {
  if (!staged[item.name]) staged[item.name] = baseModel(item);
  return staged[item.name];
}

function onCount(item, value) {
  ensure(item).counted_quantity = value;
  persistDraft();
}
function onCondition(item, value) {
  ensure(item).condition = value;
  persistDraft();
}
function onNote(item, value) {
  ensure(item).notes = value;
  persistDraft();
}

function buildLines() {
  const known = new Set(rows.value.map((r) => r.name));
  const out = [];
  for (const [name, model] of Object.entries(staged)) {
    if (!known.has(name)) continue;
    out.push({
      name,
      counted_quantity: model.counted_quantity,
      condition: model.condition,
      notes: model.notes || "",
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
  const result = await submitRes.submit({
    building: building.value,
    lines: JSON.stringify(lines),
  });
  if (submitRes.error) {
    submitError.value = resourceErrorMessage(submitRes.error, "errors.submitFailed");
    return;
  }
  const saved = (result && result.saved) || 0;
  const failed = (result && result.failed) || 0;
  toast.create({
    type: failed ? "warning" : "success",
    message: failed ? t("success.partial", { ok: saved, failed }) : t("success.saved", { n: saved }),
  });
  clearStaged();
  dropCountDraft(building.value);
  closeItem();
  invRes.reload();
}
</script>

<style scoped>
.filter {
  align-self: start;
}
.draft-note {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  color: var(--c-success);
  font-weight: var(--fw-semibold);
  font-size: var(--fs-xs);
}

.room {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.room-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding-inline: var(--sp-1);
}
.room-mark {
  display: grid;
  place-items: center;
  height: var(--sp-6);
  width: var(--sp-6);
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  color: var(--c-ink-soft);
  background: color-mix(in srgb, var(--c-ink) 8%, transparent);
}
.room-name {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
}
.room-count {
  font-size: var(--fs-sm);
  color: var(--c-muted);
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
