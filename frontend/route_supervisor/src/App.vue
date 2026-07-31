<!-- Copyright (c) 2026, AFMCO and contributors -->
<!--
  Masar Route Supervisor portal shell. Composes the four supervisor capabilities around a
  selected Route Plan:
    1. Approve / reject the plan assigned to this supervisor (native backend decision).
    2. Track boarding live per trip (BoardingPanel).
    3. Follow the ordered route stops (RoutePanel).
    4. Track the driver live on a map (DriverMap).
  The plan list (left) is row-scoped server-side to the caller's own assigned plans; this
  shell only ever renders what get_supervisor_context returns.
-->
<template>
  <div class="app" :dir="dir">
    <!-- Header -->
    <header class="app-header">
      <div class="brand">
        <div class="brand-mark"><Icon name="route" :size="22" :stroke-width="2.2" /></div>
        <div class="brand-txt">
          <span class="brand-name">{{ t("brand.name") }}</span>
          <span class="brand-sub">{{ t("brand.sub") }}</span>
        </div>
      </div>
      <div class="header-right">
        <div v-if="ctx" class="sup-chip">
          <Icon name="user" :size="15" />
          <span>{{ ctx.supervisor.full_name }}</span>
        </div>
        <div v-if="pendingCount" class="pending-chip">{{ t("header.pending", { n: pendingCount }) }}</div>
        <LangToggle variant="header" />
      </div>
    </header>

    <div class="layout">
      <!-- Plan list -->
      <aside class="plans">
        <div class="plans-head">
          <h1 class="plans-title">{{ t("list.title") }}</h1>
          <button class="ghost-btn" :title="t('common.refresh')" @click="loadContext()">
            <Icon name="refresh" :size="16" />
          </button>
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
              </div>
              <div v-if="p.trip" class="pc-boarding">
                <div class="pc-bar"><span :style="{ width: barPct(p.trip.boarding) + '%' }" /></div>
                <span class="pc-bnum">{{ p.trip.boarding.boarded }}/{{ p.trip.boarding.expected || "—" }}</span>
              </div>
            </button>
          </li>
        </ul>
      </aside>

      <!-- Main -->
      <main class="main">
        <div v-if="!selectedPlan" class="empty big">
          <Icon name="route" :size="40" :stroke-width="1.5" />
          <p>{{ t("list.empty") }}</p>
        </div>

        <template v-else>
          <!-- Plan hero -->
          <div class="hero">
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

          <!-- Tabs -->
          <nav class="tabs" role="tablist">
            <button v-for="tb in TABS" :key="tb.key" class="tab" :class="{ on: tab === tb.key }"
                    role="tab" :aria-selected="tab === tb.key" @click="tab = tb.key">
              <Icon :name="tb.icon" :size="16" /> {{ t("tabs." + tb.key) }}
            </button>
          </nav>

          <!-- Panels -->
          <div class="panel-area">
            <!-- 1. Approval -->
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
                    <div v-if="selectedPlan.decided_on" class="sb-sub">{{ t("approval.decidedOn", { at: selectedPlan.decided_on }) }}</div>
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

            <!-- 2. Boarding -->
            <BoardingPanel v-show="tab === 'boarding'" :tripName="selectedTrip" :active="tab === 'boarding'" />
            <!-- 3. Route -->
            <RoutePanel v-show="tab === 'route'" :planName="selectedPlan.name" />
            <!-- 4. Map -->
            <DriverMap v-show="tab === 'map'" :tripName="selectedTrip" :active="tab === 'map'" />
          </div>
        </template>
      </main>
    </div>

    <!-- Reject modal -->
    <div v-if="reject.open" class="overlay" @click.self="closeReject()">
      <div class="modal">
        <h3 class="modal-title">{{ t("approval.rejectTitle") }}</h3>
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

    <!-- Toast -->
    <div class="toast" :class="[toast.show ? 'show' : '', 'toast-' + toast.type]">{{ toast.msg }}</div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import Icon from "./Icon.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import { useToast } from "@shared/useToast.js";
import { usePoll } from "@shared/usePoll.js";
import BoardingPanel from "./components/BoardingPanel.vue";
import RoutePanel from "./components/RoutePanel.vue";
import DriverMap from "./components/DriverMap.vue";
import { useI18n } from "./i18n";
import { getSupervisorContext, approveRoutePlan, rejectRoutePlan } from "./api.js";
import { connectRouteSupervisorRealtime } from "./realtime.js";
import { pct } from "./fmt.js";

const { t, dir, resourceErrorMessage } = useI18n();

const TABS = [
  { key: "approval", icon: "circle-check" },
  { key: "boarding", icon: "bus" },
  { key: "route", icon: "route" },
  { key: "map", icon: "pin" },
];

const ctx = ref(null);
const loadState = ref("loading");
const loadError = ref("");
const selectedName = ref(null);
const tab = ref("approval");
const busy = ref(false);
const reject = ref({ open: false, reason: "" });
// Shared toast: every call site below passes its type explicitly, so the shared
// "green" default never reaches the `toast-*` class this portal styles.
const { toast, showToast } = useToast();
let stopRealtime = null;
const POLL_MS = 45000;

const plans = computed(() => ctx.value?.plans || []);
const pendingCount = computed(() => ctx.value?.counts?.pending || 0);
const selectedPlan = computed(() => plans.value.find((p) => p.name === selectedName.value) || null);
const selectedTrip = computed(() => selectedPlan.value?.trip?.name || null);

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

function selectPlan(name) {
  selectedName.value = name;
  tab.value = "approval";
}

async function loadContext() {
  if (!ctx.value) loadState.value = "loading";
  try {
    const res = await getSupervisorContext();
    ctx.value = res;
    loadState.value = "ready";
    loadError.value = "";
    // Keep the current selection if it still exists; else select the first plan.
    if (!res.plans.find((p) => p.name === selectedName.value)) {
      selectedName.value = res.plans[0]?.name || null;
    }
  } catch (e) {
    loadState.value = "error";
    loadError.value = resourceErrorMessage(e, "list.loadError");
  }
}

async function approve() {
  if (!selectedPlan.value || busy.value) return;
  busy.value = true;
  try {
    await approveRoutePlan(selectedPlan.value.name);
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
    await rejectRoutePlan(selectedPlan.value.name, reason);
    showToast(t("approval.rejectedToast"), "ok");
    closeReject();
    await loadContext();
  } catch (e) {
    showToast(resourceErrorMessage(e, "approval.actionError"), "bad");
  } finally {
    busy.value = false;
  }
}

// Keep the document direction/lang in sync so native RTL applies page-wide.
watch(
  dir,
  (d) => {
    document.documentElement.setAttribute("dir", d);
    document.documentElement.setAttribute("lang", d === "rtl" ? "ar" : "en");
  },
  { immediate: true },
);

// The server now announces a decision (RoutePlan.set_supervisor_decision), so the
// socket carries the update instantly instead of the supervisor waiting out a 45s
// window. The interval stays as the fallback the shared factory's swallow-everything
// contract requires: if the socket never connects, the portal must still refresh.
//
// Shared poll, not a local setInterval: this screen is where route and boarding
// plans get approved or rejected, so a supervisor returning from another tab must
// not be shown a snapshot up to a full interval old. usePoll stops the timer while
// the tab is hidden and refetches the moment it comes back.
usePoll(() => {
  if (!busy.value && !reject.value.open) loadContext();
}, POLL_MS);

onMounted(() => {
  loadContext();
  stopRealtime = connectRouteSupervisorRealtime(() => {
    if (!busy.value && !reject.value.open) loadContext();
  });
});
onUnmounted(() => {
  if (stopRealtime) stopRealtime();
});
</script>
