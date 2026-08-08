<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <TabletSupervisorShell
    :dir="dir"
    :title="t('list.title')"
    :subtitle="summary"
    :menu-label="t('nav.menu')"
  >
    <template #brand>
      <span class="brand-mark"><Brand :size="24" /></span>
      <span class="brand-txt">
        <span class="brand-name">{{ t("brand.name") }}</span>
        <span class="brand-sub">{{ t("brand.sub") }}</span>
      </span>
    </template>

    <template #nav>
      <span class="nav-label">{{ t("nav.work") }}</span>
      <button
        v-for="tb in shownTabs"
        :key="tb.key"
        type="button"
        :class="{ 'is-active': onPlan && tab === tb.key }"
        :disabled="!selectedPlan"
        @click="selectTab(tb.key)"
      >
        <Icon :name="tb.icon" :size="17" />
        <span>{{ t("tabs." + tb.key) }}</span>
        <span v-if="tb.key === 'approval' && pendingCount" class="nav-count">{{ pendingCount }}</span>
      </button>

      <button
        type="button"
        :class="{ 'is-active': onQueue }"
        @click="openQueue()"
      >
        <Icon name="circle-check" :size="17" />
        <span>{{ t("queue.title") }}</span>
        <span v-if="pendingCount" class="nav-count">{{ pendingCount }}</span>
      </button>

      <button
        type="button"
        :class="{ 'is-active': onFleetMap }"
        @click="openFleetMap()"
      >
        <Icon name="pin" :size="17" />
        <span>{{ t("fleetMap.title") }}</span>
      </button>

      <span class="nav-label">{{ t("nav.account") }}</span>
      <span v-if="ctx" class="nav-user">
        <Icon name="user" :size="16" />
        <span>{{ ctx.supervisor.full_name }}</span>
      </span>
    </template>

    <template #title-actions>
      <button
        type="button"
        class="ghost-btn"
        :title="t('common.refresh')"
        :aria-label="t('common.refresh')"
        @click="loadContext()"
      >
        <Icon name="refresh" :size="16" />
      </button>
      <LangToggle />
    </template>

    <template #kpis>
      <div class="kpi">
        <span class="kpi-label">{{ t("kpi.pending") }}</span>
        <b class="kpi-num">{{ pendingCount }}</b>
      </div>
      <div class="kpi">
        <span class="kpi-label">{{ t("kpi.active") }}</span>
        <b class="kpi-num">{{ totalCount }}</b>
      </div>
      <div v-if="selectedBoarding" class="kpi">
        <span class="kpi-label">{{ t("kpi.boarding") }}</span>
        <b class="kpi-num">{{ selectedBoarding.boarded }}/{{ selectedBoarding.expected || "—" }}</b>
      </div>
    </template>

    <div v-if="onQueue" class="work work-single">
      <ApprovalQueue
        :plans="plans"
        :busy="busy"
        @open="selectPlan"
        @approve="approvePlan"
        @reject="rejectPlan"
      />
    </div>

    <div v-else-if="onFleetMap" class="work work-single">
      <FleetMap />
    </div>

    <div v-else class="work">
      <aside v-if="showList" class="plans">
        <div class="plans-head">
          <h2 class="plans-title">{{ t("header.plans") }}</h2>
        </div>

        <div v-if="loadState === 'loading'" class="plan-skel">
          <div v-for="n in 4" :key="n" class="skeleton-card" />
        </div>
        <div v-else-if="loadState === 'error'" class="empty">
          <Icon name="triangle-alert" :size="28" :stroke-width="1.6" />
          <p>{{ loadError || t("list.loadError") }}</p>
          <button class="soft-btn" @click="loadContext()">{{ t("common.retry") }}</button>
        </div>
        <div v-else-if="!plans.length" class="empty">
          <Icon name="clipboard-check" :size="30" :stroke-width="1.6" />
          <p>{{ t("list.empty") }}</p>
        </div>

        <ul v-else class="plan-list">
          <li v-for="p in plans" :key="p.name">
            <button class="plan-card" :class="{ sel: p.name === selectedName }" @click="selectPlan(p.name)">
              <div class="pc-top">
                <span class="pc-name">{{ p.route_name || p.name }}</span>
                <span class="badge" :class="'bd-' + p.approval.toLowerCase()">{{ t("approval." + p.approval) }}</span>
              </div>
              <div class="pc-meta">
                <span v-if="p.project"><Icon name="badge" :size="12" /> {{ p.project }}</span>
                <span v-if="p.shift"><Icon name="clock" :size="12" /> {{ t("shift." + p.shift) }}</span>
                <span><Icon name="pin" :size="12" /> {{ t("list.stops", { n: p.total_stops }) }}</span>
                <span v-if="wide && p.driver"><Icon name="user" :size="12" /> {{ p.driver }}</span>
                <span v-if="wide && p.vehicle"><Icon name="truck" :size="12" /> {{ p.vehicle }}</span>
              </div>
              <div v-if="p.trip" class="pc-boarding">
                <div class="pc-bar"><span :style="{ width: barPct(p.trip.boarding) + '%' }" /></div>
                <span class="pc-bnum">{{ p.trip.boarding.boarded }}/{{ p.trip.boarding.expected || "—" }}</span>
              </div>
            </button>
          </li>
        </ul>
      </aside>

      <section v-if="showDetail" class="detail">
        <div v-if="!selectedPlan" class="empty big">
          <Icon name="route" :size="40" :stroke-width="1.5" />
          <p>{{ t("list.empty") }}</p>
        </div>

        <template v-else>
          <div class="hero">
            <button v-if="narrow" type="button" class="back-btn" :aria-label="t('nav.plans')" @click="backToList()">
              <Icon name="chevron" :size="18" />
            </button>
            <div class="hero-main">
              <h2 class="hero-title">{{ selectedPlan.route_name || selectedPlan.name }}</h2>
              <div class="hero-chips">
                <span v-if="selectedPlan.project" class="hc"><Icon name="badge" :size="13" /> {{ selectedPlan.project }}</span>
                <span v-if="selectedPlan.shift" class="hc"><Icon name="clock" :size="13" /> {{ t("shift." + selectedPlan.shift) }}</span>
                <span v-if="selectedPlan.driver" class="hc"><Icon name="user" :size="13" /> {{ selectedPlan.driver }}</span>
                <span v-if="selectedPlan.vehicle" class="hc"><Icon name="truck" :size="13" /> {{ selectedPlan.vehicle }}</span>
                <span class="hc"><Icon name="pin" :size="13" /> {{ t("list.stops", { n: selectedPlan.total_stops }) }}</span>
              </div>
            </div>
            <span class="badge lg" :class="'bd-' + selectedPlan.approval.toLowerCase()">{{ t("approval." + selectedPlan.approval) }}</span>
          </div>

          <nav class="tabs" role="tablist">
            <button v-for="tb in shownTabs" :key="tb.key" class="tab" :class="{ on: tab === tb.key }"
                    role="tab" :aria-selected="tab === tb.key" @click="selectTab(tb.key)">
              <Icon :name="tb.icon" :size="16" /> {{ t("tabs." + tb.key) }}
            </button>
          </nav>

          <div class="panel-area">
            <section v-show="tab === 'approval'" class="panel">
              <header class="panel-head">
                <div>
                  <h2 class="panel-title">{{ t("approval.status") }}</h2>
                  <p class="panel-sub">{{ statusHint }}</p>
                </div>
              </header>

              <div class="approval-body">
                <div class="status-block" :class="'sb-' + selectedPlan.approval.toLowerCase()">
                  <Icon :name="statusIcon" :size="30" :stroke-width="1.8" />
                  <div>
                    <div class="sb-label">{{ t("approval." + selectedPlan.approval) }}</div>
                    <div v-if="selectedPlan.decided_on" class="sb-sub">{{ t("approval.decidedOn", { at: agoLabel(selectedPlan.decided_on, lang) }) }}</div>
                  </div>
                </div>

                <div v-if="selectedPlan.approval === 'Rejected' && selectedPlan.rejection_reason" class="reason-box">
                  <span class="rb-label">{{ t("approval.reason") }}</span>
                  <p>{{ selectedPlan.rejection_reason }}</p>
                </div>

                <div v-if="selectedPlan.approval === 'Pending'" class="approve-actions">
                  <button class="primary-btn" :disabled="busy" @click="approve()">
                    <Icon name="check" :size="17" /> {{ busy ? t("approval.approving") : t("approval.approve") }}
                  </button>
                  <button class="danger-btn" :disabled="busy" @click="openReject()">
                    <Icon name="x" :size="17" /> {{ t("approval.reject") }}
                  </button>
                </div>
              </div>
            </section>

            <BoardingPanel v-show="tab === 'boarding'" :tripName="selectedTrip" :active="tab === 'boarding'" />
            <RoutePanel v-show="tab === 'route'" :planName="selectedPlan.name" />
            <DriverMap v-if="!wide" v-show="tab === 'map'" :tripName="selectedTrip" :active="tab === 'map'" />
          </div>
        </template>
      </section>

      <aside v-if="wide && selectedPlan" class="live">
        <DriverMap :tripName="selectedTrip" :active="true" />
      </aside>
    </div>

    <div v-if="reject.open" class="overlay" @click.self="closeReject()">
      <div ref="rejectEl" class="modal" role="dialog" aria-modal="true" aria-labelledby="reject-title">
        <h3 id="reject-title" class="modal-title">{{ t("approval.rejectTitle") }}</h3>
        <p class="modal-sub">{{ t("approval.rejectPrompt") }}</p>
        <textarea v-model="reject.reason" class="modal-input" rows="4" :placeholder="t('approval.rejectPlaceholder')" />
        <div class="modal-btns">
          <button class="soft-btn" @click="closeReject()">{{ t("common.cancel") }}</button>
          <button class="danger-btn" :disabled="busy" @click="confirmReject()">
            <Icon name="x" :size="15" /> {{ t("approval.rejectConfirm") }}
          </button>
        </div>
      </div>
    </div>

    <div class="toast" :class="[toast.show ? 'show' : '', 'toast-' + toast.type]">{{ toast.msg }}</div>
  </TabletSupervisorShell>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import Icon from "./Icon.vue";
import Brand from "@shared/components/Brand.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import TabletSupervisorShell from "@shared/components/TabletSupervisorShell.vue";
import { useToast } from "@shared/useToast.js";
import { usePoll } from "@shared/usePoll.js";
import { useOverlay } from "@shared/useOverlay.js";
import BoardingPanel from "./components/BoardingPanel.vue";
import RoutePanel from "./components/RoutePanel.vue";
import DriverMap from "./components/DriverMap.vue";
import FleetMap from "./components/FleetMap.vue";
import ApprovalQueue from "./components/ApprovalQueue.vue";
import { useI18n } from "./i18n";
import { useDocumentLanguage } from "@shared/useDocumentLanguage";
import { getSupervisorContext, approveRoutePlan, rejectRoutePlan } from "./api.js";
import { connectRouteSupervisorRealtime } from "./realtime.js";
import { pct, agoLabel } from "./fmt.js";

const { t, lang, dir, resourceErrorMessage } = useI18n();

const TABS = [
  { key: "approval", icon: "circle-check" },
  { key: "boarding", icon: "bus" },
  { key: "route", icon: "route" },
  { key: "map", icon: "pin" },
];

const FLEET_MAP_ROUTE = "#/map";
const QUEUE_ROUTE = "#/approvals";
const onFleetMap = ref(false);
const onQueue = ref(false);

/* The menu holds two groups of buttons — the plan's tabs, and the two whole-screen
   destinations — and each group knew only its own state. So the tab you last opened stayed lit
   while you moved to the queue, and two items looked selected at once. One flag settles it:
   a tab is current only while a plan is what the screen is showing. */
const onPlan = computed(() => !onQueue.value && !onFleetMap.value);

function readFleetMapRoute() {
  /* The hash is the ONLY writer of these two flags. Setting them anywhere else lets the screen
     and the address disagree, and then a tab click changes the URL while the queue stays on
     top of it. */
  const hash = window.location.hash || "";
  onFleetMap.value = hash.startsWith(FLEET_MAP_ROUTE);
  onQueue.value = hash.startsWith(QUEUE_ROUTE);
}

function goTo(target) {
  /* Every navigation in this screen goes through here: push only when the address really
     changes, then re-derive the view from it. Pushing an unchanged hash costs a back press
     that does nothing, and skipping the re-read leaves the menu lit on the wrong item. */
  if (window.location.hash !== target) window.history.pushState(null, "", target);
  readFleetMapRoute();
}

function openFleetMap() {
  goTo(FLEET_MAP_ROUTE);
}

function openQueue() {
  goTo(QUEUE_ROUTE);
}

function selectTab(key) {
  /* Assigning `tab` its CURRENT value changes no ref, so the watcher below never fires and
     nothing reconciles — which is why tapping the tab you are already on used to do nothing
     at all while the queue stayed on screen. Reconcile here instead of relying on the watcher. */
  tab.value = key;
  routeToLocation();
}

async function approvePlan(name) {
  /* Acts on the card that was tapped, without moving the selection. Selecting it first was a
     navigation as far as the watcher was concerned, so approving from the queue jumped him
     out of the queue — but only for cards that were not already selected. */
  await approve(name);
}

function rejectPlan(name) {
  rejecting.value = name;
  openReject();
}

const ctx = ref(null);
const loadState = ref("loading");
const loadError = ref("");
const selectedName = ref(null);
const tab = ref("approval");
const busy = ref(false);
const reject = ref({ open: false, reason: "" });
/* The plan the reject dialog is about, when it was opened from a queue card rather than from
   the open plan. Keeping it here instead of moving the selection is what stops a rejection
   from navigating him somewhere he did not ask to go. */
const rejecting = ref(null);
const rejectEl = ref(null);
useOverlay({
  active: () => reject.value.open,
  container: rejectEl,
  close: () => closeReject(),
});
const { toast, showToast } = useToast();
let stopRealtime = null;
const POLL_MS = 45000;

const plans = computed(() => ctx.value?.plans || []);
const pendingCount = computed(() => ctx.value?.counts?.pending || 0);
const totalCount = computed(() => ctx.value?.counts?.total || 0);
const selectedPlan = computed(() => plans.value.find((p) => p.name === selectedName.value) || null);
const selectedTrip = computed(() => selectedPlan.value?.trip?.name || null);
const selectedBoarding = computed(() => selectedPlan.value?.trip?.boarding || null);

const summary = computed(() => t("header.summary", { p: pendingCount.value, t: totalCount.value }));

const statusHint = computed(() => {
  const a = selectedPlan.value?.approval;
  return a === "Pending" ? t("approval.pendingHint") : t("approval." + a);
});
const statusIcon = computed(
  () => ({ Pending: "clock", Approved: "circle-check", Rejected: "x" })[selectedPlan.value?.approval] || "clock",
);

function barPct(b) {
  return pct(b.boarded, b.expected);
}

const TAB_KEYS = TABS.map((tb) => tb.key);

const WIDE_QUERY = "(min-width: 1280px)";
const NARROW_QUERY = "(max-width: 640px)";
const wide = ref(typeof window !== "undefined" && window.matchMedia(WIDE_QUERY).matches);
const narrow = ref(typeof window !== "undefined" && window.matchMedia(NARROW_QUERY).matches);
let wideMedia = null;
let narrowMedia = null;

function onWidthChange(event) {
  wide.value = event.matches;
  if (wide.value && tab.value === "map") tab.value = TAB_KEYS[0];
}

function onNarrowChange(event) {
  narrow.value = event.matches;
}

const showList = computed(() => !narrow.value || !selectedName.value);
const showDetail = computed(() => !narrow.value || Boolean(selectedName.value));

function backToList() {
  selectedName.value = null;
}

const shownTabs = computed(() => (wide.value ? TABS.filter((tb) => tb.key !== "map") : TABS));

function routeFromLocation() {
  const match = (window.location.hash || "").match(/^#\/plan\/([^/]+)(?:\/([a-z]+))?/);
  if (!match) return null;
  /* A wide layout draws the map beside the plan instead of as a tab, so `map` is not a tab it
     can show. A link carrying it would otherwise land on an empty panel with the tab lit. */
  const asked = match[2];
  const offered = shownTabs.value.some((tb) => tb.key === asked);
  return {
    name: decodeURIComponent(match[1]),
    tab: offered ? asked : TAB_KEYS[0],
  };
}

function routeToLocation() {
  const target = selectedName.value
    ? `#/plan/${encodeURIComponent(selectedName.value)}/${tab.value}`
    : "#/";
  if (window.location.hash !== target) window.history.pushState(null, "", target);
  readFleetMapRoute();
}

function applyRoute() {
  const route = routeFromLocation();
  if (!route) return false;
  if (plans.value.some((p) => p.name === route.name)) selectedName.value = route.name;
  tab.value = route.tab;
  return true;
}

function selectPlan(name) {
  /* Sets the plan and lets the URL watcher clear the queue and map flags. Clearing them here
     as well left the address on #/approvals, and the next history event read it back. */
  selectedName.value = name;
  tab.value = TAB_KEYS[0];
  routeToLocation();
}

async function loadContext() {
  if (!ctx.value) loadState.value = "loading";
  try {
    const res = await getSupervisorContext();
    ctx.value = res;
    loadState.value = "ready";
    loadError.value = "";
    /* Only pick a plan for him while a plan is what the screen is showing. Doing it on the
       queue or the map moved `selectedName`, and the watcher below read that as an intent to
       navigate — so a reload on the queue, or approving any card but the first, threw him into
       a plan he had not opened. */
    if (
      onPlan.value
      && !applyRoute()
      && !narrow.value
      && !res.plans.find((p) => p.name === selectedName.value)
    ) {
      selectedName.value = res.plans[0]?.name || null;
    }
  } catch (e) {
    loadState.value = "error";
    loadError.value = resourceErrorMessage(e, "list.loadError");
  }
}

async function approve(name) {
  const target = name || selectedPlan.value?.name;
  if (!target || busy.value) return;
  busy.value = true;
  try {
    await approveRoutePlan(target);
    showToast(t("approval.approvedToast"), "ok");
    await loadContext();
  } catch (e) {
    showToast(resourceErrorMessage(e, "approval.actionError"), "bad");
  } finally {
    busy.value = false;
  }
}

function openReject() {
  reject.value = { open: true, reason: "" };
}
function closeReject() {
  reject.value.open = false;
  rejecting.value = null;
}
async function confirmReject() {
  const reason = (reject.value.reason || "").trim();
  if (!reason) {
    showToast(t("approval.reasonRequired"), "bad");
    return;
  }
  if (busy.value) return;
  busy.value = true;
  try {
    await rejectRoutePlan(rejecting.value || selectedPlan.value?.name, reason);
    showToast(t("approval.rejectedToast"), "ok");
    closeReject();
    await loadContext();
  } catch (e) {
    showToast(resourceErrorMessage(e, "approval.actionError"), "bad");
  } finally {
    busy.value = false;
  }
}

useDocumentLanguage(lang, dir);

usePoll(() => {
  if (!busy.value && !reject.value.open) loadContext();
}, POLL_MS);

watch([selectedName, tab], routeToLocation);

onMounted(() => {
  loadContext();
  wideMedia = window.matchMedia(WIDE_QUERY);
  wideMedia.addEventListener("change", onWidthChange);
  onWidthChange(wideMedia);
  narrowMedia = window.matchMedia(NARROW_QUERY);
  narrowMedia.addEventListener("change", onNarrowChange);
  onNarrowChange(narrowMedia);
  readFleetMapRoute();
  window.addEventListener("hashchange", readFleetMapRoute);
  window.addEventListener("popstate", readFleetMapRoute);
  window.addEventListener("hashchange", applyRoute);
  window.addEventListener("popstate", applyRoute);
  stopRealtime = connectRouteSupervisorRealtime(() => {
    if (!busy.value && !reject.value.open) loadContext();
  });
});
onUnmounted(() => {
  if (wideMedia) wideMedia.removeEventListener("change", onWidthChange);
  if (narrowMedia) narrowMedia.removeEventListener("change", onNarrowChange);
  window.removeEventListener("hashchange", readFleetMapRoute);
  window.removeEventListener("popstate", readFleetMapRoute);
  window.removeEventListener("hashchange", applyRoute);
  window.removeEventListener("popstate", applyRoute);
  if (stopRealtime) stopRealtime();
});
</script>
