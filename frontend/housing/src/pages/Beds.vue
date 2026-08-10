<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <ListSkeleton v-if="gridRes.loading && !grid" :rows="6" :label="t('beds.loadingLabel')" />

  <LoadError
    v-else-if="gridRes.error"
    :title="t('errors.gridFailed')"
    :detail="gridErrorMessage"
    :hint="t('errors.retryHint')"
    :retry-label="t('common.retry')"
    @retry="gridRes.reload()"
  />

  <EmptyState
    v-else-if="!hasBeds"
    :title="t('building.emptyBoardTitle')"
    :hint="t('building.emptyBoardHint')"
  >
    <template #icon><Icon name="bed" :size="24" /></template>
    <template #action>
      <Button size="xl" variant="outline" :label="t('empty.switch')" @click="onChangeBuilding" />
    </template>
  </EmptyState>

  <template v-else>
    <div class="section-head">
      <h2>{{ t("beds.title") }}</h2>
      <Badge theme="green" size="lg" :label="summaryLabel" />
      <Badge
        v-if="openRequests"
        theme="orange"
        size="lg"
        :label="t('beds.openRequests', { n: openRequests })"
      />
      <!-- Zero open requests and a failed read drew the same picture: no badge. -->
      <Badge
        v-else-if="requestsRes.error"
        theme="gray"
        size="lg"
        :label="t('errors.requestsUnknown')"
      />
      <Button variant="ghost" size="md" :label="t('common.refresh')" @click="reloadAll">
        <template #icon><Icon name="refresh" :size="18" /></template>
      </Button>
    </div>

    <BedGrid
      :grid="grid"
      :can-set-readiness="canReadiness"
      @bed="onBed"
      @room="openReadiness"
    />

    <Dialog
      :modelValue="!!readinessRoom"
      :options="{ title: t('beds.readiness'), size: 'sm' }"
      @update:modelValue="(open) => !open && (readinessRoom = null)"
    >
      <template #body-content>
        <div class="stack-tight">
          <Button
            v-for="status in READINESS"
            :key="status"
            size="2xl"
            :variant="readinessRoom && readinessRoom.readiness_status === status ? 'solid' : 'outline'"
            :loading="busy === status"
            :label="tEnum('readiness', status)"
            @click="setReadiness(status)"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      :modelValue="!!checkInBed"
      :options="{ title: checkInTitle, size: 'lg' }"
      @update:modelValue="(open) => !open && closeSheet()"
    >
      <template #body-content>
        <div class="stack">
          <FormControl
            type="text"
            size="lg"
            :label="t('beds.scanOrType')"
            v-model="identifier"
            @keyup.enter="resolve"
          />
          <Button
            size="xl"
            variant="subtle"
            :loading="resolving"
            :label="t('beds.resolve')"
            @click="resolve"
          >
            <template #prefix><Icon name="search" :size="18" /></template>
          </Button>

          <div v-if="worker" class="worker-card">
            <img v-if="worker.image" class="worker-photo" :src="worker.image" alt="" />
            <span v-else class="worker-photo worker-photo-blank"><Icon name="user" :size="20" /></span>
            <div class="worker-body">
              <b>{{ worker.employee_name || worker.party }}</b>
              <small>{{ tEnum("custody", worker.party_type) }}</small>
            </div>
          </div>
          <p v-if="worker && worker.has_active_assignment" class="status-note status-warn">
            {{ t("beds.alreadyHoused") }}
          </p>

          <!-- Without this the operator cannot tell a permission gap from a dead call:
               the select is simply empty and check-in stays disabled with no reason. -->
          <FormControl
            v-if="worker"
            type="select"
            size="lg"
            :label="t('beds.project')"
            :options="projectOptions"
            :description="projectsRes.error ? t('errors.listFailed') : undefined"
            v-model="project"
          />
          <FormControl
            v-if="worker"
            type="date"
            size="lg"
            :label="t('beds.checkInDate')"
            v-model="checkInDate"
          />

          <ErrorMessage v-if="sheetError" :message="sheetError" />
          <p v-if="!canCheckIn" class="hint">{{ t("access.needCheckIn") }}</p>
        </div>
      </template>
      <template #actions>
        <Button
          class="dock-btn"
          size="2xl"
          variant="solid"
          theme="green"
          :disabled="!canCheckIn || !worker || !project || worker.has_active_assignment"
          :loading="busy === 'check-in'"
          :label="t('beds.checkIn')"
          @click="doCheckIn"
        />
      </template>
    </Dialog>

    <Dialog
      :modelValue="!!occupantBed"
      :options="{ title: checkOutTitle, size: 'lg' }"
      @update:modelValue="(open) => !open && closeSheet()"
    >
      <template #body-content>
        <div v-if="occupant" class="stack">
          <div class="worker-card">
            <span class="worker-photo worker-photo-blank"><Icon name="user" :size="20" /></span>
            <div class="worker-body">
              <b>{{ occupant.employee_name }}</b>
              <small>{{ occupant.project }} · {{ occupant.check_in_date }}</small>
            </div>
          </div>

          <p v-if="occupant.has_custody" class="status-note status-warn">
            {{ t("beds.custodyBlockBody", { name: occupant.employee_name }) }}
          </p>

          <template v-else>
            <FormControl
              type="date"
              size="lg"
              :label="t('beds.checkOutDate')"
              v-model="checkOutDate"
            />
            <FormControl
              type="select"
              size="lg"
              :label="t('beds.checkOutReason')"
              :options="reasonOptions"
              v-model="checkOutReason"
            />
          </template>

          <ErrorMessage v-if="sheetError" :message="sheetError" />
          <p v-if="!canCheckOut" class="hint">{{ t("access.needCheckOut") }}</p>
        </div>
      </template>
      <template #actions>
        <div class="sheet-actions">
          <Button
            v-if="occupant && occupant.has_custody"
            class="dock-btn"
            size="2xl"
            variant="solid"
            :disabled="!custodySection"
            :label="t('beds.custodyBlockGo')"
            @click="goToCustody"
          />
          <Button
            v-else
            class="dock-btn"
            size="2xl"
            variant="solid"
            theme="red"
            :disabled="!canCheckOut || !checkOutReason"
            :loading="busy === 'check-out'"
            :label="t('beds.checkOut')"
            @click="doCheckOut"
          />
        </div>
      </template>
    </Dialog>
  </template>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Badge,
  Button,
  Dialog,
  ErrorMessage,
  FormControl,
  createListResource,
  createResource,
  toast,
} from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import BedGrid from "../components/BedGrid.vue";
import Icon from "../components/Icon.vue";
import ListSkeleton from "../components/ListSkeleton.vue";
import LoadError from "../components/LoadError.vue";
import { call } from "@shared/call";
import { useI18n, apiErrorMessage, resourceErrorMessage } from "../i18n";
import { can, hasSection } from "../portal.js";
import { building, clearBuilding, localDate } from "../session";

const { t, tEnum } = useI18n();
const route = useRoute();
const router = useRouter();

const API = "apex.habitat.api.front_desk.";
const READINESS = ["Ready", "Needs Cleaning", "Needs Repair", "Out of Service", "Unknown"];
const REASONS = [
  "Final Exit",
  "Internal Transfer",
  "Project Transfer",
  "Absconding",
  "End of Contract",
];

const canReadiness = can("set_readiness");
const canCheckIn = can("check_in");
const canCheckOut = can("check_out");
const custodySection = hasSection("custody");

const busy = ref("");
const sheetError = ref("");
const readinessRoom = ref(null);
const checkInBed = ref(null);
const occupantBed = ref(null);
const occupant = ref(null);
const worker = ref(null);
const pendingWorker = ref(null);
const identifier = ref("");
const resolving = ref(false);
const project = ref("");
const checkInDate = ref(localDate());
const checkOutDate = ref(localDate());
const checkOutReason = ref("");

const gridRes = createResource({
  url: API + "get_building_grid",
  makeParams: () => ({ building: building.value }),
});

const requestsRes = createResource({
  url: API + "building_open_requests",
  makeParams: () => ({ building: building.value }),
});

const projectsRes = createListResource({
  doctype: "Project",
  fields: ["name", "project_name"],
  orderBy: "modified desc",
  pageLength: 200,
  auto: true,
});

const grid = computed(() => gridRes.data || null);
const gridErrorMessage = computed(() => resourceErrorMessage(gridRes.error, "errors.gridFailed"));
const hasBeds = computed(() => !!(grid.value && grid.value.floors && grid.value.floors.length));
const openRequests = computed(() => (requestsRes.data && requestsRes.data.open_requests) || 0);

const summaryLabel = computed(() => {
  const s = (grid.value && grid.value.summary) || {};
  const total = Number(s.total_beds || 0);
  return t("beds.summary", { occupied: Number(s.occupied || 0), total });
});

const projectOptions = computed(() => [
  { label: t("beds.project"), value: "" },
  ...(projectsRes.data || []).map((p) => ({ label: p.project_name || p.name, value: p.name })),
]);

const reasonOptions = computed(() =>
  REASONS.map((value) => ({ label: tEnum("beds.reason", value), value })),
);

const checkInTitle = computed(() =>
  checkInBed.value ? t("beds.checkInTitle", { bed: checkInBed.value.bed_code }) : "",
);
const checkOutTitle = computed(() =>
  occupant.value ? t("beds.checkOutTitle", { name: occupant.value.employee_name }) : "",
);

function reloadAll() {
  gridRes.reload();
  requestsRes.reload();
}

function findBed(bedName) {
  const floors = (grid.value && grid.value.floors) || [];
  for (const floor of floors) {
    for (const room of floor.rooms || []) {
      const hit = (room.beds || []).find((b) => b.bed === bedName);
      if (hit) return hit;
    }
  }
  return null;
}

function fetchAll() {
  if (!building.value) return;
  gridRes.fetch();
  requestsRes.fetch();
}

function onChangeBuilding() {
  clearBuilding();
}

async function loadPendingWorker(party_type, party) {
  try {
    const found = await call(API + "describe_worker", { args: { party_type, party } });
    pendingWorker.value = found && found.found ? found : null;
    if (!found || !found.found) {
      toast.create({ type: "error", message: (found && found.message) || t("errors.workerFailed") });
    }
  } catch (err) {
    pendingWorker.value = null;
    toast.create({ type: "error", message: apiErrorMessage(err) });
  }
}

watch(building, () => {
  closeSheet();
  fetchAll();
});

onMounted(() => {
  fetchAll();
  const q = route.query;
  if (q.party_type && q.party) loadPendingWorker(String(q.party_type), String(q.party));
});

function closeSheet() {
  checkInBed.value = null;
  occupantBed.value = null;
  occupant.value = null;
  worker.value = null;
  identifier.value = "";
  project.value = "";
  sheetError.value = "";
  checkOutReason.value = "";
  if (route.params.bed) router.replace("/beds");
}

function onBed(bed) {
  sheetError.value = "";
  worker.value = null;
  identifier.value = "";
  project.value = "";
  checkInDate.value = localDate();
  checkOutDate.value = localDate();
  checkOutReason.value = "";
  if (bed.bed_color === "red") {
    occupantBed.value = bed;
    occupant.value = bed.occupant;
    checkInBed.value = null;
    return;
  }
  checkInBed.value = bed;
  occupantBed.value = null;
  occupant.value = null;
  if (pendingWorker.value) worker.value = pendingWorker.value;
}

function openReadiness(room) {
  readinessRoom.value = room;
}

async function setReadiness(status) {
  const room = readinessRoom.value;
  if (!room || busy.value) return;
  busy.value = status;
  try {
    await call(API + "set_room_readiness", { args: { room: room.room, status }, type: "POST" });
    toast.create({ type: "success", message: t("beds.readinessSet") });
    readinessRoom.value = null;
    reloadAll();
  } catch (err) {
    toast.create({ type: "error", message: apiErrorMessage(err) });
  } finally {
    busy.value = "";
  }
}

async function resolve() {
  const code = identifier.value.trim();
  if (!code || resolving.value) return;
  resolving.value = true;
  sheetError.value = "";
  worker.value = null;
  try {
    const found = await call(API + "resolve_worker", { args: { identifier: code } });
    if (!found || !found.found) {
      sheetError.value = (found && found.message) || t("custody.scanNoMatch", { code });
      return;
    }
    worker.value = found;
  } catch (err) {
    sheetError.value = apiErrorMessage(err);
  } finally {
    resolving.value = false;
  }
}

async function doCheckIn() {
  const bed = checkInBed.value;
  if (!bed || !worker.value || busy.value) return;
  busy.value = "check-in";
  sheetError.value = "";
  try {
    await call(API + "quick_check_in", {
      args: {
        bed: bed.bed,
        party_type: worker.value.party_type,
        party: worker.value.party,
        employee: worker.value.employee || null,
        project: projectValue(),
        check_in_date: checkInDate.value,
      },
      type: "POST",
    });
    toast.create({ type: "success", message: t("beds.checkedIn") });
    pendingWorker.value = null;
    closeSheet();
    reloadAll();
  } catch (err) {
    sheetError.value = apiErrorMessage(err);
  } finally {
    busy.value = "";
  }
}

function projectValue() {
  const value = project.value;
  return value && typeof value === "object" ? value.value : value;
}

async function doCheckOut() {
  const bed = occupantBed.value;
  if (!bed || busy.value) return;
  busy.value = "check-out";
  sheetError.value = "";
  try {
    const result = await call(API + "quick_check_out", {
      args: {
        bed: bed.bed,
        checkout_date: checkOutDate.value,
        checkout_reason: checkOutReason.value,
      },
      type: "POST",
    });
    if (result && result.requires_full_form) {
      sheetError.value = t("beds.custodyBlockTitle");
      await gridRes.reload();
      const fresh = findBed(bed.bed);
      if (fresh) {
        occupantBed.value = fresh;
        occupant.value = fresh.occupant;
      }
      return;
    }
    toast.create({ type: "success", message: t("beds.checkedOut") });
    closeSheet();
    reloadAll();
  } catch (err) {
    sheetError.value = apiErrorMessage(err);
  } finally {
    busy.value = "";
  }
}

function goToCustody() {
  const party = occupant.value || {};
  closeSheet();
  router.push({
    path: "/custody",
    query: { party_type: party.party_type, party: party.party, mode: "return" },
  });
}
</script>

<style scoped>
.worker-card {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding-block: var(--sp-3);
  border-block: var(--border-width) solid var(--c-border);
  background: transparent;
}
.worker-photo {
  block-size: 44px;
  inline-size: 44px;
  border-radius: var(--radius-pill);
  object-fit: cover;
  flex-shrink: 0;
}
.worker-photo-blank {
  display: grid;
  place-items: center;
  color: var(--c-muted);
  background: color-mix(in srgb, var(--c-ink) 8%, transparent);
}
.worker-body {
  min-inline-size: 0;
  display: flex;
  flex-direction: column;
}
.worker-body small {
  font-size: var(--fs-xs);
  color: var(--c-muted);
}
</style>
