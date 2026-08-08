<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <BuildingPicker v-if="!building" @select="onBuildingSelected" />

  <template v-else>
    <TabButtons
      class="filter"
      v-model="mode"
      :dir="dir"
      :buttons="[
        { label: t('custody.issue'), value: 'issue' },
        { label: t('custody.return'), value: 'return' },
      ]"
    />

    <section v-if="!party" class="stack">
      <h2 class="section-title">{{ t("custody.pickWorker") }}</h2>
      <FormControl
        type="select"
        size="lg"
        :label="t('custody.workerType')"
        :options="partyTypeOptions"
        v-model="partyType"
      />
      <ScanField @code="onScan" />
      <FormControl
        type="text"
        size="lg"
        :label="t('custody.searchWorker')"
        v-model="query"
      />
      <ul v-if="matches.length" class="stack-tight">
        <li v-for="row in matches" :key="row.name">
          <Button
            class="wide"
            size="xl"
            variant="outline"
            :label="row.label"
            @click="selectParty(partyType, row.name, row.label)"
          />
        </li>
      </ul>
      <p v-else-if="query.trim() && !searchRes.loading" class="hint">{{ t("arrivals.searchEmpty") }}</p>
      <p v-if="scanError" class="status-note status-err">{{ scanError }}</p>
    </section>

    <template v-else>
      <div class="section-head">
        <h2>{{ party.party_name }}</h2>
        <Button variant="ghost" size="md" :label="t('common.change')" @click="clearParty">
          <template #icon><Icon name="user" :size="18" /></template>
        </Button>
      </div>

      <ListSkeleton v-if="loading" :rows="5" :label="t('common.loading')" />

      <LoadError
        v-else-if="loadError"
        :title="t('errors.custodyFailed')"
        :detail="loadError"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="reload"
      />

      <template v-else-if="mode === 'issue'">
        <EmptyState v-if="!articles.length" :title="t('custody.catalogEmpty')">
          <template #icon><Icon name="box" :size="24" /></template>
        </EmptyState>

        <ul v-else class="tiles">
          <li v-for="art in articles" :key="art.article" class="tile">
            <div class="tile-head">
              <img v-if="art.image" class="tile-img" :src="art.image" alt="" />
              <span v-else class="tile-img tile-img-blank"><Icon name="box" :size="18" /></span>
              <div class="tile-body">
                <b>{{ art.article_name }}</b>
                <small v-if="art.store_balance !== null">
                  {{ art.store_balance > 0 ? t("custody.inStore", { n: art.store_balance }) : t("custody.noStock") }}
                </small>
              </div>
            </div>
            <Stepper
              :model-value="issueQty(art.article)"
              :min="0"
              :max="9999"
              :disabled="!canIssue"
              :label="art.article_name"
              @update:model-value="(qty) => setIssueQty(art, qty)"
            />
          </li>
        </ul>
      </template>

      <template v-else>
        <EmptyState v-if="!heldLines.length" :title="t('custody.holdingEmpty')">
          <template #icon><Icon name="check-circle" :size="24" /></template>
        </EmptyState>

        <ul v-else class="tiles">
          <li v-for="line in heldLines" :key="lineKey(line)" class="tile">
            <div class="tile-head">
              <span class="tile-img tile-img-blank"><Icon name="box" :size="18" /></span>
              <div class="tile-body">
                <b>{{ line.article_name }}</b>
                <small>{{ t("custody.issuedOn", { date: line.issue_date }) }} · {{ line.qty }} {{ line.uom || "" }}</small>
              </div>
            </div>
            <Stepper
              :model-value="returnQty(line)"
              :min="0"
              :max="line.qty"
              :disabled="!canReturn"
              :label="line.article_name"
              @update:model-value="(qty) => setReturnQty(line, qty)"
            />
            <FormControl
              v-if="returnQty(line) > 0"
              type="select"
              size="md"
              :label="t('custody.conditionBack')"
              :options="conditionOptions"
              :model-value="returnCondition(line)"
              @update:model-value="(value) => setReturnCondition(line, value)"
            />
          </li>
        </ul>
      </template>

      <div class="hz-dock">
        <ErrorMessage v-if="actionError" class="dock-error" :message="actionError" />
        <Button
          class="dock-btn"
          size="2xl"
          variant="solid"
          theme="green"
          :disabled="!cartCount || (mode === 'issue' ? !canIssue : !canReturn)"
          :loading="!!busy"
          :loading-text="mode === 'issue' ? t('custody.issuing') : t('custody.returning')"
          :label="mode === 'issue' ? t('custody.issueCta', { n: cartCount }) : t('custody.returnCta', { n: cartCount })"
          @click="commit"
        >
          <template #prefix><Icon name="send" :size="20" /></template>
        </Button>
        <p class="dock-hint">{{ dockHint }}</p>
      </div>
    </template>
  </template>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  Button,
  ErrorMessage,
  FormControl,
  TabButtons,
  createListResource,
  createResource,
  toast,
} from "frappe-ui";
import BuildingPicker from "@shared/components/BuildingPicker.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import ListSkeleton from "../components/ListSkeleton.vue";
import LoadError from "../components/LoadError.vue";
import ScanField from "../components/ScanField.vue";
import Stepper from "../components/Stepper.vue";
import { call } from "@shared/call";
import { useI18n, apiErrorMessage, resourceErrorMessage } from "../i18n";
import { can } from "../portal.js";
import { building, selectBuilding } from "../session";

const { t, tEnum, dir } = useI18n();
const route = useRoute();

const API = "apex.habitat.api.custody_kiosk.";
const RETURN_CONDITIONS = ["Good", "Fair", "Damaged", "Lost"];

const canIssue = can("issue_custody");
const canReturn = can("return_custody");

const mode = ref(route.query.mode === "return" ? "return" : "issue");
const partyType = ref("Employee");
const party = ref(null);
const query = ref("");
const scanError = ref("");
const actionError = ref("");
const busy = ref("");

const issueCart = reactive({});
const returnCart = reactive({});

const catalogRes = createResource({
  url: API + "get_kiosk_catalog",
  makeParams: () => ({ building: building.value }),
});

const heldRes = createResource({
  url: API + "get_party_custody",
  makeParams: () => ({
    party_type: (party.value && party.value.party_type) || "",
    party: (party.value && party.value.party) || "",
  }),
});

const searchRes = createListResource({
  doctype: "Employee",
  fields: ["name", "employee_name"],
  pageLength: 20,
});

const partyTypeOptions = computed(() =>
  ["Employee", "Temporary Worker"].map((value) => ({ label: tEnum("custody", value), value })),
);

const conditionOptions = computed(() =>
  RETURN_CONDITIONS.map((value) => ({ label: tEnum("returnCondition", value), value })),
);

const matches = computed(() => {
  if (!query.value.trim()) return [];
  return (searchRes.data || []).map((row) => ({
    name: row.name,
    label: row.employee_name || row.worker_name || row.name,
  }));
});

const articles = computed(() => (catalogRes.data && catalogRes.data.articles) || []);
const heldLines = computed(() => (heldRes.data && heldRes.data.lines) || []);

const loading = computed(() =>
  mode.value === "issue" ? catalogRes.loading && !articles.value.length : heldRes.loading,
);
const loadError = computed(() => {
  const err = mode.value === "issue" ? catalogRes.error : heldRes.error;
  return err ? apiErrorMessage(err, "errors.custodyFailed") : "";
});

const cartCount = computed(() =>
  mode.value === "issue" ? Object.keys(issueCart).length : Object.keys(returnCart).length,
);

const dockHint = computed(() => {
  if (mode.value === "issue" && !canIssue) return t("access.needIssue");
  if (mode.value === "return" && !canReturn) return t("access.needReturn");
  if (!cartCount.value) return t("custody.cartEmpty");
  return t("custody.cartLines", { n: cartCount.value });
});

function lineKey(line) {
  return line.custody_issue + "|" + line.article;
}

function issueQty(article) {
  return issueCart[article] ? issueCart[article].qty : 0;
}

function setIssueQty(art, qty) {
  if (qty > 0) issueCart[art.article] = { article: art.article, qty };
  else delete issueCart[art.article];
}

function returnQty(line) {
  const held = returnCart[lineKey(line)];
  return held ? held.qty : 0;
}

function returnCondition(line) {
  const held = returnCart[lineKey(line)];
  return held ? held.condition_on_return : "Good";
}

function setReturnQty(line, qty) {
  const key = lineKey(line);
  if (qty <= 0) {
    delete returnCart[key];
    return;
  }
  returnCart[key] = {
    custody_issue: line.custody_issue,
    article: line.article,
    qty,
    condition_on_return: returnCart[key] ? returnCart[key].condition_on_return : "Good",
  };
}

function setReturnCondition(line, value) {
  const key = lineKey(line);
  if (!returnCart[key]) return;
  returnCart[key] = { ...returnCart[key], condition_on_return: value };
}

function clearCarts() {
  for (const k of Object.keys(issueCart)) delete issueCart[k];
  for (const k of Object.keys(returnCart)) delete returnCart[k];
  actionError.value = "";
}

function selectParty(type, name, label) {
  party.value = { party_type: type, party: name, party_name: label || name };
  query.value = "";
  scanError.value = "";
  clearCarts();
  loadForParty();
}

function clearParty() {
  party.value = null;
  clearCarts();
}

function loadForParty() {
  if (!party.value) return;
  heldRes.fetch();
}

function reload() {
  if (mode.value === "issue") catalogRes.reload();
  else heldRes.reload();
}

async function onScan(code) {
  scanError.value = "";
  try {
    const found = await call(API + "resolve_scan", {
      args: { code, party_type: partyType.value, building: building.value },
    });
    if (found && found.kind === "worker") {
      partyType.value = found.party_type;
      selectParty(found.party_type, found.party, found.party_name);
      return;
    }
    if (found && found.kind === "article" && party.value && mode.value === "issue") {
      setIssueQty(found.article, issueQty(found.article.article) + 1);
      return;
    }
    scanError.value = t("custody.scanNoMatch", { code });
  } catch (err) {
    scanError.value = apiErrorMessage(err);
  }
}

async function commit() {
  if (busy.value || !party.value) return;
  busy.value = mode.value;
  actionError.value = "";
  try {
    if (mode.value === "issue") {
      await call(API + "issue_cart", {
        args: {
          building: building.value,
          party_type: party.value.party_type,
          party: party.value.party,
          items_json: JSON.stringify(Object.values(issueCart)),
        },
        type: "POST",
      });
      toast.create({ type: "success", message: t("custody.issued") });
    } else {
      await call(API + "return_cart", {
        args: {
          party_type: party.value.party_type,
          party: party.value.party,
          items_json: JSON.stringify(Object.values(returnCart)),
        },
        type: "POST",
      });
      toast.create({ type: "success", message: t("custody.returned") });
    }
    clearCarts();
    catalogRes.reload();
    heldRes.reload();
  } catch (err) {
    actionError.value = apiErrorMessage(err);
  } finally {
    busy.value = "";
  }
}

function onBuildingSelected(name, label) {
  selectBuilding(name, label);
}

watch(building, () => {
  clearCarts();
  if (building.value) catalogRes.fetch();
});

watch(mode, () => {
  actionError.value = "";
  if (mode.value === "issue") catalogRes.fetch();
  else loadForParty();
});

watch([query, partyType], () => {
  const term = query.value.trim();
  if (!term) return;
  const isEmployee = partyType.value === "Employee";
  const titleField = isEmployee ? "employee_name" : "worker_name";
  searchRes.update({
    doctype: partyType.value,
    fields: ["name", titleField],
    filters: { [titleField]: ["like", "%" + term + "%"] },
  });
  searchRes.reload();
});

onMounted(() => {
  if (building.value) catalogRes.fetch();
  const q = route.query;
  if (q.party_type && q.party) selectParty(String(q.party_type), String(q.party), String(q.party));
});
</script>

<style scoped>
.filter {
  align-self: start;
}
.wide {
  width: 100%;
  min-height: var(--tap-min);
}
.tiles {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.tile {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3);
  border-radius: var(--radius);
  border: var(--border-width) solid var(--c-border);
  background: var(--c-surface-2);
}
.tile-head {
  flex: 1;
  min-width: 160px;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.tile-img {
  height: 40px;
  width: 40px;
  border-radius: var(--radius-sm);
  object-fit: cover;
  flex-shrink: 0;
}
.tile-img-blank {
  display: grid;
  place-items: center;
  color: var(--c-muted);
  background: color-mix(in srgb, var(--c-ink) 8%, transparent);
}
.tile-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.tile-body small {
  font-size: var(--fs-xs);
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
