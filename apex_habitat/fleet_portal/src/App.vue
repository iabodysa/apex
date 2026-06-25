<script setup>
/*
 * Fleet OS supervisor board — Vue 3 port of the supervisor's hand-made
 * www/fleet.html design. The markup/classes mirror his original 1:1 so the
 * verbatim CSS in index.css styles it identically; the data is live (the
 * fleet_os whitelisted API) instead of his embedded JSON. The six fleet
 * actions are wired to their POST endpoints through src/api.js's call().
 *
 * Omitted by design (per the port brief): the brand version line + save-label,
 * persist()/autoSave()/updateSaveLabel(), the Export modal, and the
 * WhatsApp/email/save-folder/file-import cluster. Frappe is the datastore, so
 * there is no client-side save/export. The add-vehicle / office-manager /
 * fuel-rate / damage / accident sub-forms from the original are client-only
 * persistence with no backing endpoint, so the panel renders their (empty)
 * read views — the only write surfaces kept are the six real endpoints.
 */
import { ref, reactive, computed, onMounted, watch } from "vue";
import { call } from "./api.js";
import Icon from "./components/Icon.vue";
import LangToggle from "./components/LangToggle.vue";
import { useI18n } from "./i18n";

const { t, dir } = useI18n();

// Keep the document direction/lang in sync so native RTL applies page-wide.
watch(
  dir,
  (d) => {
    document.documentElement.setAttribute("dir", d);
    document.documentElement.setAttribute("lang", d === "rtl" ? "ar" : "en");
  },
  { immediate: true },
);

// ═══════════ DATA ═══════════
const vehicles = ref([]);
const loadState = ref("loading"); // loading | ready | error
const loadError = ref("");
// Typed empty reason from the API: scope_empty | data_empty | null.
const loadReason = ref(null);

const GET = "apex_habitat.salis.api.fleet_os.get_fleet_os";
const POST = (m) => "apex_habitat.salis.api.fleet_os." + m;

// Normalize a fetched vehicle to the shape his render code reads (defends the
// client-only fields the live API leaves empty/null).
function normalize(v) {
  if (!Array.isArray(v.damages)) v.damages = [];
  if (!Array.isArray(v.accidents)) v.accidents = [];
  if (v.stolen_info === undefined) v.stolen_info = null;
  if (!Array.isArray(v.history)) v.history = [];
  return v;
}

async function loadFleet() {
  loadState.value = "loading";
  try {
    const r = await call(GET);
    vehicles.value = ((r && r.vehicles) || []).map(normalize);
    loadReason.value = (r && r.reason) || null;
    loadState.value = "ready";
  } catch (e) {
    loadError.value = serverMsg(e);
    loadState.value = "error";
  }
}
// Re-pull after a successful write (keeps the panel in sync if it is open).
async function reloadFleet() {
  try {
    const r = await call(GET);
    vehicles.value = ((r && r.vehicles) || []).map(normalize);
    loadReason.value = (r && r.reason) || null;
  } catch (e) {
    /* keep the last good list; the action toast already reported success */
  }
  if (panel.open && panel.plate) {
    const fresh = vehicles.value.find((x) => x.plate === panel.plate);
    if (fresh) panel.vehicle = fresh;
    else closePanel();
  }
}
onMounted(loadFleet);

// Frappe surfaces thrown errors as a JSON-encoded _server_messages array; pull
// the human message out of whatever shape arrived.
function serverMsg(e) {
  let raw = (e && e.message) || String(e || "");
  try {
    const parsed = JSON.parse(raw);
    const arr = Array.isArray(parsed) ? parsed : [parsed];
    const msgs = arr.map((m) => {
      try {
        const o = typeof m === "string" ? JSON.parse(m) : m;
        return o.message || o;
      } catch (_) {
        return m;
      }
    });
    raw = msgs.join(" — ");
  } catch (_) {
    /* not JSON — use as-is */
  }
  return String(raw).replace(/<[^>]*>/g, "").trim();
}

// ═══════════ HELPERS (ported from his JS) ═══════════
function today() {
  return new Date().toISOString().split("T")[0];
}
function calcDur(from, to) {
  if (!from) return "";
  const d1 = new Date(from);
  const d2 = to ? new Date(to) : new Date();
  const days = Math.round((d2 - d1) / 86400000);
  if (isNaN(days) || days < 0) return "";
  if (days > 365) return t("duration.months", { n: Math.round(days / 30) });
  return t("duration.days", { n: days });
}
function calcTotalDaysNum(v) {
  if (!v.history.length) return 0;
  const first = v.history[0].date_receive;
  if (!first) return 0;
  return Math.max(0, Math.round((new Date() - new Date(first)) / 86400000));
}
function calcActiveDaysNum(v) {
  return v.history.reduce((s, h) => {
    if (!h.date_receive) return s;
    const d1 = new Date(h.date_receive);
    const d2 = h.date_deliver ? new Date(h.date_deliver) : new Date();
    return s + Math.max(0, Math.round((d2 - d1) / 86400000));
  }, 0);
}
const trim = (x) => (x || "").toString().trim();

// Status badge meta (his SB map): static class + icon; the label is resolved
// reactively via t() so it follows the language toggle.
const SB = {
  assigned: { cls: "sb-assigned", ic: "lock" },
  available: { cls: "sb-available", ic: "circle-dot" },
  workshop: { cls: "sb-workshop", ic: "wrench" },
  stopped: { cls: "sb-stopped", ic: "circle-pause" },
  stolen: { cls: "sb-stolen", ic: "shield-alert" },
};
const statusKey = (s) => (SB[s] ? s : "stopped");
const sb = (v) => {
  const k = statusKey(v.vehicle_status);
  return { ...SB[k], label: t("status." + k) };
};
// Table short label for a status.
const sl = (s) => t("statusShort." + statusKey(s));
// Sheet-type icon name (car vs motorcycle).
const icon = (v) => (v.sheet === "CAR" ? "car" : "bike");
const initials = (d) => (d ? (d.name_ar || d.name_en || "") : "").slice(0, 2);

// ═══════════ FILTER STATE (mirrors his applyFilters) ═══════════
const f = reactive({
  search: "",
  status: "",
  sheet: "",
  fuel: "",
  project: "",
  area: "",
  office: "",
  dateType: "receive",
  dateFrom: "",
  dateTo: "",
  sort: "plate",
  view: "cards",
});
// Table column sort (his sortCol toggling).
const sortCol = ref("plate");
const sortDir = ref(1);

function setSP(s) {
  f.status = s;
}
function setSheet(v) {
  f.sheet = v;
}
function setFuel(v) {
  f.fuel = v;
}
function setDateType(v) {
  f.dateType = v;
}
function setView(v) {
  f.view = v;
}
function onSortCol(col) {
  if (sortCol.value === col) sortDir.value *= -1;
  else {
    sortCol.value = col;
    sortDir.value = 1;
  }
}
function setQuickDate(days) {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - days);
  f.dateFrom = from.toISOString().split("T")[0];
  f.dateTo = to.toISOString().split("T")[0];
}
function clearDateFilter() {
  f.dateFrom = "";
  f.dateTo = "";
}
function resetFilters() {
  f.search = "";
  f.status = "";
  f.sheet = "";
  f.fuel = "";
  f.project = "";
  f.area = "";
  f.office = "";
  f.dateType = "receive";
  f.dateFrom = "";
  f.dateTo = "";
  sortCol.value = "plate";
  sortDir.value = 1;
}
const hasDateFilter = computed(() => !!(f.dateFrom || f.dateTo));
// No project is in scope for this user (an access gap, not just an empty board).
const isScopeEmpty = computed(() => loadReason.value === "scope_empty");

const anyFilterActive = computed(
  () =>
    !!(
      f.search ||
      f.status ||
      f.sheet ||
      f.fuel ||
      f.project ||
      f.area ||
      f.office ||
      f.dateFrom ||
      f.dateTo
    )
);

// The filtered + sorted list — a faithful port of his applyFilters body.
const filtered = computed(() => {
  const q = f.search.toLowerCase();
  let list = vehicles.value.filter((v) => {
    if (f.status && v.vehicle_status !== f.status) return false;
    if (f.sheet && v.sheet !== f.sheet) return false;
    if (f.fuel && !(v.fuel || "").includes(f.fuel)) return false;
    if (f.project && trim(v.project) !== f.project) return false;
    if (f.area && trim(v.area) !== f.area) return false;
    if (f.office && trim(v.rental_office) !== f.office) return false;
    if (q) {
      const d = v.current_driver;
      const hay = [
        v.plate,
        v.vehicle_type,
        v.rental_office,
        v.area,
        d ? d.name_ar : "",
        d ? d.name_en : "",
        d ? d.driver_id : "",
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (f.dateFrom || f.dateTo) {
      const match = v.history.some((h) => {
        let dates = [];
        if (f.dateType === "receive") dates = [h.date_receive];
        else if (f.dateType === "deliver") dates = [h.date_deliver];
        else dates = [h.date_receive, h.date_deliver];
        return dates.some((d) => {
          if (!d) return false;
          if (f.dateFrom && d < f.dateFrom) return false;
          if (f.dateTo && d > f.dateTo) return false;
          return true;
        });
      });
      if (!match) return false;
    }
    return true;
  });

  const sort = f.sort;
  list = list.slice().sort((a, b) => {
    if (sort === "drivers_desc") return b.history.length - a.history.length;
    if (sort === "duration_desc")
      return calcTotalDaysNum(b) - calcTotalDaysNum(a);
    const va = (a[sort] || "").toString();
    const vb = (b[sort] || "").toString();
    return va.localeCompare(vb, "ar") * sortDir.value;
  });
  return list;
});

// Header pill / sidebar stat counts (his updateStats, over the full fleet).
const counts = computed(() => {
  const all = vehicles.value;
  const by = (s) => all.filter((v) => v.vehicle_status === s).length;
  const drivers = new Set(
    all.flatMap((v) => v.history.map((h) => h.driver_id)).filter(Boolean)
  );
  return {
    total: all.length,
    assigned: by("assigned"),
    available: by("available"),
    workshop: by("workshop"),
    stopped: by("stopped"),
    stolen: by("stolen"),
    drivers: drivers.size,
  };
});

const dateInfo = computed(() => {
  if (!hasDateFilter.value) return "";
  const typeKey = { receive: "receive", deliver: "deliver", any: "anyDate" }[f.dateType];
  return t("dateInfo.summary", {
    n: filtered.value.length,
    type: t("sidebar." + typeKey),
    from: f.dateFrom || "…",
    to: f.dateTo || t("common.today"),
  });
});

// Enriched empty-state chips describing which filters are active.
const activeFilterChips = computed(() => {
  const c = [];
  if (f.search) c.push(t("chip.search", { v: f.search }));
  if (f.status) c.push(t("chip.status", { v: t("status." + statusKey(f.status)) }));
  if (f.sheet) c.push(t("chip.type", { v: f.sheet }));
  if (f.fuel) c.push(t("chip.fuel", { v: f.fuel }));
  if (f.project) c.push(t("chip.project", { v: f.project }));
  if (f.area) c.push(t("chip.area", { v: f.area }));
  if (f.office) c.push(t("chip.office", { v: f.office }));
  if (f.dateFrom || f.dateTo)
    c.push(t("chip.date", { from: f.dateFrom || "…", to: f.dateTo || t("common.today") }));
  return c;
});

// ═══════════ PANEL ═══════════
const panel = reactive({ open: false, plate: "", tab: 0, vehicle: null });
const subForm = ref(null); // null | reassign | stop | stolen

function openPanel(plate, tab = 0) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  panel.vehicle = v;
  panel.plate = plate;
  panel.tab = tab;
  panel.open = true;
  subForm.value = null;
}
function closePanel() {
  panel.open = false;
  panel.vehicle = null;
  panel.plate = "";
  subForm.value = null;
}
function setPTab(idx) {
  panel.tab = idx;
  subForm.value = null;
}

const tabDmg = computed(() => (panel.vehicle?.damages || []).length);
const tabAcc = computed(() => (panel.vehicle?.accidents || []).length);

// ═══════════ TOAST ═══════════
const toast = reactive({ msg: "", type: "green", show: false });
let toastTimer = null;
function showToast(msg, type = "green") {
  toast.msg = msg;
  toast.type = type;
  toast.show = true;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.show = false), 3500);
}

// ═══════════ CONFIRM ENGINE (his cfShow, promise-based) ═══════════
// `icon` here is a Lucide icon name (rendered via <Icon> in the modal).
const cf = reactive({
  open: false,
  icon: "triangle-alert",
  title: "",
  msg: "",
  okLabel: "",
  okCls: "btn-blue",
});
let cfResolve = null;
function cfShow(title, msg, icon = "triangle-alert", okLabel = t("confirm.ok"), okCls = "btn-blue") {
  cf.title = title;
  cf.msg = msg;
  cf.icon = icon;
  cf.okLabel = okLabel;
  cf.okCls = okCls;
  cf.open = true;
  return new Promise((resolve) => {
    cfResolve = resolve;
  });
}
function cfDo(val) {
  cf.open = false;
  if (cfResolve) {
    cfResolve(val);
    cfResolve = null;
  }
}

// ═══════════ ACTIONS → endpoints ═══════════
// Reassign sub-form model (the only fields the live reassign endpoint uses are
// driver_id + date; the rest mirror his form but aren't sent server-side).
const rf = reactive({ nameAr: "", nameEn: "", iqama: "", mobile: "", project: "KEETA", area: "RIYADH", date: today(), branch: "" });
function openReassignForm() {
  Object.assign(rf, {
    nameAr: "",
    nameEn: "",
    iqama: "",
    mobile: "",
    project: "KEETA",
    area: "RIYADH",
    date: today(),
    branch: "",
  });
  subForm.value = "reassign";
}
async function submitReassign() {
  const v = panel.vehicle;
  if (!v) return;
  if (!trim(rf.nameAr) || !trim(rf.iqama)) {
    showToast(t("toast.nameIqamaRequired"), "amber");
    return;
  }
  const ok = await cfShow(
    t("confirm.reassignTitle"),
    t("confirm.reassignMsg", { name: trim(rf.nameAr), plate: v.plate }),
    "lock",
    t("confirm.reassignOk"),
    "btn-green"
  );
  if (!ok) return;
  try {
    await call(POST("reassign"), {
      type: "POST",
      args: { plate: v.plate, driver_id: trim(rf.iqama), date: rf.date || today() },
    });
    showToast(t("toast.reassigned", { name: trim(rf.nameAr), plate: v.plate }), "green");
    subForm.value = null;
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}

// Stop sub-form model. nextStatus is the post-stop status: optionally chain
// workshop_in / recover so the live state matches.
const sf = reactive({ date: today(), branch: "", reason: "", notes: "", nextStatus: "available" });
function openStopForm() {
  Object.assign(sf, { date: today(), branch: "", reason: "", notes: "", nextStatus: "available" });
  subForm.value = "stop";
}
async function confirmStop() {
  const v = panel.vehicle;
  if (!v || !v.current_driver) return;
  const drName = v.current_driver.name_ar || v.current_driver.name_en || t("logTab.driver");
  const ok = await cfShow(
    t("confirm.stopTitle"),
    t("confirm.stopMsg", { name: drName, plate: v.plate }),
    "circle-pause",
    t("confirm.stopOk"),
    "btn-red"
  );
  if (!ok) return;
  const reason = sf.notes ? `${sf.reason} — ${sf.notes}` : sf.reason;
  try {
    await call(POST("stop_vehicle"), {
      type: "POST",
      args: { plate: v.plate, reason },
    });
    if (sf.nextStatus === "workshop")
      await call(POST("workshop_in"), { type: "POST", args: { plate: v.plate } });
    else if (sf.nextStatus === "available")
      await call(POST("recover"), { type: "POST", args: { plate: v.plate } });
    const label =
      sf.nextStatus === "available"
        ? t("toast.statusAvailable")
        : sf.nextStatus === "workshop"
          ? t("toast.statusWorkshop")
          : t("toast.statusStopped");
    showToast(t("toast.stopped", { status: label }), "green");
    subForm.value = null;
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}

// Stolen sub-form model → report_theft (the live endpoint takes location +
// report_number; date/reporter/description mirror his form but aren't sent).
const stf = reactive({ date: today(), police: "", location: "", reporter: "", desc: "", notes: "" });
function openStolenForm() {
  Object.assign(stf, { date: today(), police: "", location: "", reporter: "", desc: "", notes: "" });
  subForm.value = "stolen";
}
async function submitStolen() {
  const v = panel.vehicle;
  if (!v) return;
  const ok = await cfShow(
    t("confirm.stolenTitle"),
    t("confirm.stolenMsg", { plate: v.plate }),
    "shield-alert",
    t("confirm.stolenOk"),
    "btn-red"
  );
  if (!ok) return;
  try {
    await call(POST("report_theft"), {
      type: "POST",
      args: { plate: v.plate, location: trim(stf.location), report_number: trim(stf.police) },
    });
    showToast(t("toast.theftReported"), "amber");
    subForm.value = null;
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}

// Quick card actions (his quickStop / quickReassign / sendWorkshop / …).
function quickStop(plate, goWorkshop = false) {
  openPanel(plate, 1);
  openStopForm();
  if (goWorkshop) sf.nextStatus = "workshop";
}
function quickReassign(plate) {
  openPanel(plate, 1);
  openReassignForm();
}
async function sendWorkshop(plate) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  if (v.current_driver) {
    showToast(t("toast.stopBeforeWorkshop"), "amber");
    return;
  }
  const ok = await cfShow(
    t("confirm.sendWorkshopTitle"),
    t("confirm.sendWorkshopMsg", { plate }),
    "wrench",
    t("confirm.sendWorkshopOk"),
    "btn-amber"
  );
  if (!ok) return;
  try {
    await call(POST("workshop_in"), { type: "POST", args: { plate } });
    showToast(t("toast.sentToWorkshop"), "amber");
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}
async function exitWorkshop(plate) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  const ok = await cfShow(
    t("confirm.exitWorkshopTitle"),
    t("confirm.exitWorkshopMsg", { plate }),
    "circle-check",
    t("confirm.exitWorkshopOk"),
    "btn-green"
  );
  if (!ok) return;
  try {
    await call(POST("workshop_out"), { type: "POST", args: { plate } });
    showToast(t("toast.leftWorkshop"), "green");
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}
async function setAvailable(plate) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  const ok = await cfShow(
    t("confirm.setAvailableTitle"),
    t("confirm.setAvailableMsg", { plate }),
    "circle-dot",
    t("confirm.ok"),
    "btn-blue"
  );
  if (!ok) return;
  try {
    await call(POST("recover"), { type: "POST", args: { plate } });
    showToast(t("toast.availableAtOffice"), "green");
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}
async function recoverVehicle(plate) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  const ok = await cfShow(
    t("confirm.recoverTitle"),
    t("confirm.recoverMsg", { plate }),
    "lock-open",
    t("confirm.recoverOk"),
    "btn-green"
  );
  if (!ok) return;
  try {
    await call(POST("recover"), { type: "POST", args: { plate } });
    showToast(t("toast.recovered"), "green");
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}
function markStolen(plate) {
  openPanel(plate, 2);
  openStolenForm();
}

// Status-picker grid in the panel Status tab → routes to the right endpoint.
async function changeStatus(plate, newStatus) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  if (newStatus === v.vehicle_status) return;
  if (newStatus === "assigned" && !v.current_driver) {
    showToast(t("toast.noDriverAssignFirst"), "amber");
    return;
  }
  if (newStatus === "assigned") {
    openReassignForm();
    return;
  }
  if (
    (newStatus === "workshop" || newStatus === "available" || newStatus === "stopped" || newStatus === "stolen") &&
    v.current_driver
  ) {
    showToast(t("toast.stopCurrentFirst"), "amber");
    return;
  }
  if (newStatus === "stolen") {
    openStolenForm();
    return;
  }
  const icons = { assigned: "lock", available: "circle-dot", workshop: "wrench", stopped: "circle-pause" };
  const ok = await cfShow(
    t("confirm.changeStatusTitle"),
    t("confirm.changeStatusMsg", {
      plate,
      from: t("status." + statusKey(v.vehicle_status)),
      to: t("status." + statusKey(newStatus)),
    }),
    icons[newStatus] || "triangle-alert",
    t("confirm.changeStatusOk"),
    "btn-blue"
  );
  if (!ok) return;
  const wasWorkshop = v.vehicle_status === "workshop";
  try {
    if (newStatus === "workshop") await call(POST("workshop_in"), { type: "POST", args: { plate } });
    else if (newStatus === "available")
      await call(POST(wasWorkshop ? "workshop_out" : "recover"), { type: "POST", args: { plate } });
    else if (newStatus === "stopped")
      await call(POST("stop_vehicle"), { type: "POST", args: { plate, reason: "" } });
    showToast(t("toast.statusUpdated"), "green");
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}

// Merged timeline (his buildHistoryPanel — driver spells only; the event log
// was a client-only construct, so this renders the live assignment history).
function historyItems(v) {
  return v.history
    .map((h) => ({ d: h, date: h.date_receive || "0000" }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

// Fuel display values (his cardHTML IIFE). The live API has no fuel_rate /
// fuel_grade, so these render the "—" empty path exactly as his does.
function fuelView(v) {
  const fuelType = trim(v.fuel).toUpperCase();
  const isDiesel = fuelType === "DESIL" || fuelType === "DIESEL";
  const grade = v.fuel_grade || (isDiesel ? "DIESEL" : "91");
  const gradeLabel =
    grade === "DIESEL"
      ? t("fuelGrade.diesel")
      : grade === "95"
        ? t("fuelGrade.petrol95")
        : t("fuelGrade.petrol91");
  const sarPerL = grade === "DIESEL" ? 0.69 : grade === "95" ? 2.33 : 2.18;
  const dailySAR = v.fuel_rate || 0;
  return {
    gradeLabel,
    sarPerL,
    dailySAR,
    sarDisplay: dailySAR > 0 ? dailySAR.toFixed(1) : "—",
    monDisplay: dailySAR > 0 ? (dailySAR * 30).toFixed(0) : "—",
  };
}
</script>

<template>
  <!-- TOPBAR -->
  <div class="topbar">
    <div class="brand">
      <div class="brand-badge"><Icon name="car" :size="20" /></div>
      <div>
        <div class="brand-name">{{ t("brand.name") }}</div>
      </div>
    </div>
    <div class="search-bar">
      <span class="si"><Icon name="search" :size="15" /></span>
      <input v-model="f.search" :placeholder="t('topbar.searchPlaceholder')" />
    </div>
    <div class="status-pills">
      <span class="sp sp-all" :class="{ active: f.status === '' }" @click="setSP('')">{{ counts.total }} {{ t("topbar.allVehicles") }}</span>
      <span class="sp sp-assigned" :class="{ active: f.status === 'assigned' }" @click="setSP('assigned')">{{ counts.assigned }} {{ t("statusShort.assigned") }}</span>
      <span class="sp sp-available" :class="{ active: f.status === 'available' }" @click="setSP('available')">{{ counts.available }} {{ t("statusShort.available") }}</span>
      <span class="sp sp-workshop" :class="{ active: f.status === 'workshop' }" @click="setSP('workshop')">{{ counts.workshop }} {{ t("statusShort.workshop") }}</span>
      <span class="sp sp-stopped" :class="{ active: f.status === 'stopped' }" @click="setSP('stopped')">{{ counts.stopped }} {{ t("statusShort.stopped") }}</span>
      <span class="sp sp-stolen" :class="{ active: f.status === 'stolen' }" @click="setSP('stolen')">{{ counts.stolen }} {{ t("statusShort.stolen") }}</span>
    </div>
    <LangToggle />
  </div>

  <div class="layout">
    <!-- SIDEBAR -->
    <div class="sidebar">
      <div class="sidebar-header"><span class="sidebar-title"><Icon name="funnel" :size="13" /> {{ t("sidebar.filtersAndStats") }}</span></div>
      <div class="sidebar-scroll">
        <div class="fg">
          <div class="fl">{{ t("sidebar.vehicleType") }}</div>
          <div class="fchips">
            <button class="fchip" :class="{ on: f.sheet === '' }" @click="setSheet('')">{{ t("sidebar.all") }}</button>
            <button class="fchip" :class="{ on: f.sheet === 'CAR' }" @click="setSheet('CAR')"><Icon name="car" :size="15" /> {{ t("sidebar.cars") }}</button>
            <button class="fchip" :class="{ on: f.sheet === 'MOTORCYCLE' }" @click="setSheet('MOTORCYCLE')"><Icon name="bike" :size="15" /> {{ t("sidebar.bikes") }}</button>
          </div>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.project") }}</div>
          <select class="fs" v-model="f.project">
            <option value="">{{ t("sidebar.all") }}</option>
            <option>KEETA</option><option>KEEMART</option><option>SHIPMENT</option>
            <option>NINJA</option><option>NOON</option><option>ARAMEX</option>
            <option>STARLINKS</option>
            <option>NINJA-DIEANA</option>
          </select>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.area") }}</div>
          <select class="fs" v-model="f.area">
            <option value="">{{ t("sidebar.all") }}</option>
            <option>RIYADH</option><option>JADAH</option><option>MAKA</option>
            <option>DAMAM</option><option>TAIF</option><option>MAJMA</option>
            <option>KHARJ</option><option>YANBU</option>
          </select>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.rentalOffice") }}</div>
          <select class="fs" v-model="f.office">
            <option value="">{{ t("sidebar.all") }}</option>
            <option>AFMCO</option><option>SAFI - T</option><option>SAFI - R</option>
            <option>WASEL</option><option>TRAFEL</option>
          </select>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.fuel") }}</div>
          <div class="fchips">
            <button class="fchip" :class="{ on: f.fuel === '' }" @click="setFuel('')">{{ t("sidebar.all") }}</button>
            <button class="fchip" :class="{ on: f.fuel === 'PETROL' }" @click="setFuel('PETROL')"><Icon name="fuel" :size="15" /> {{ t("sidebar.petrol") }}</button>
            <button class="fchip" :class="{ on: f.fuel === 'DESIL' }" @click="setFuel('DESIL')"><Icon name="fuel" :size="15" /> {{ t("sidebar.diesel") }}</button>
          </div>
        </div>
        <div class="sep"></div>
        <div class="fg">
          <div class="fl"><Icon name="calendar" :size="13" /> {{ t("sidebar.dateSearchType") }}</div>
          <div class="fchips">
            <button class="fchip" :class="{ on: f.dateType === 'receive' }" @click="setDateType('receive')">{{ t("sidebar.receive") }}</button>
            <button class="fchip" :class="{ on: f.dateType === 'deliver' }" @click="setDateType('deliver')">{{ t("sidebar.deliver") }}</button>
            <button class="fchip" :class="{ on: f.dateType === 'any' }" @click="setDateType('any')">{{ t("sidebar.anyDate") }}</button>
          </div>
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.dateFrom") }}</div>
          <input type="date" class="fs" v-model="f.dateFrom" />
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.dateTo") }}</div>
          <input type="date" class="fs" v-model="f.dateTo" />
        </div>
        <div class="fg">
          <div class="fl">{{ t("sidebar.quickRange") }}</div>
          <div class="fchips" style="flex-wrap:wrap">
            <button class="fchip" @click="setQuickDate(7)">{{ t("sidebar.days7") }}</button>
            <button class="fchip" @click="setQuickDate(30)">{{ t("sidebar.month1") }}</button>
            <button class="fchip" @click="setQuickDate(90)">{{ t("sidebar.months3") }}</button>
            <button class="fchip" @click="setQuickDate(180)">{{ t("sidebar.months6") }}</button>
            <button class="fchip" @click="setQuickDate(365)">{{ t("sidebar.year1") }}</button>
            <button class="fchip" @click="clearDateFilter">{{ t("sidebar.clear") }}</button>
          </div>
        </div>
        <div v-if="hasDateFilter" style="font-size:10px;color:var(--t3);padding:4px 0">{{ dateInfo }}</div>
        <div class="sep"></div>
        <button class="btn" style="width:100%;justify-content:center" @click="resetFilters"><Icon name="rotate-cw" :size="15" /> {{ t("sidebar.reset") }}</button>
        <div class="sep"></div>
        <div class="fl" style="margin-bottom:8px"><Icon name="chart-column" :size="13" /> {{ t("sidebar.quickStats") }}</div>
        <div class="stat-mini-grid">
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--blue-l)">{{ counts.total }}</div><div class="stat-mini-l">{{ t("sidebar.total") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--green-l)">{{ counts.assigned }}</div><div class="stat-mini-l">{{ t("sidebar.assigned") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--cyan-l)">{{ counts.available }}</div><div class="stat-mini-l">{{ t("sidebar.available") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--orange-l)">{{ counts.workshop }}</div><div class="stat-mini-l">{{ t("sidebar.workshop") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--t3)">{{ counts.stopped }}</div><div class="stat-mini-l">{{ t("sidebar.stopped") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--purple-l)">{{ counts.stolen }}</div><div class="stat-mini-l">{{ t("sidebar.stolen") }}</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--blue-l)">{{ counts.drivers }}</div><div class="stat-mini-l">{{ t("sidebar.drivers") }}</div></div>
        </div>
      </div>
    </div>

    <!-- MAIN -->
    <div class="main">
      <div class="main-header">
        <div style="display:flex;align-items:center;gap:10px">
          <span class="rcount">{{ t("main.vehicleCount", { n: filtered.length }) }}</span>
          <select class="fs" style="width:auto;font-size:11px" v-model="f.sort">
            <option value="plate">{{ t("main.sortBy", { field: t("main.sortPlate") }) }}</option>
            <option value="status">{{ t("main.sortBy", { field: t("main.sortStatus") }) }}</option>
            <option value="vehicle_type">{{ t("main.sortBy", { field: t("main.sortType") }) }}</option>
            <option value="drivers_desc">{{ t("main.sortBy", { field: t("main.sortMostDrivers") }) }}</option>
            <option value="duration_desc">{{ t("main.sortBy", { field: t("main.sortLongestRunning") }) }}</option>
          </select>
        </div>
        <div class="view-tabs">
          <button class="vt" :class="{ on: f.view === 'cards' }" @click="setView('cards')"><Icon name="layout-grid" :size="14" /> {{ t("main.cards") }}</button>
          <button class="vt" :class="{ on: f.view === 'table' }" @click="setView('table')"><Icon name="list" :size="14" /> {{ t("main.table") }}</button>
        </div>
      </div>

      <!-- ERROR (persistent banner + retry) -->
      <div v-if="loadState === 'error'" class="fp-error-banner">
        <span style="color:var(--red-l)"><Icon name="triangle-alert" :size="20" /></span>
        <span class="fp-err-msg">{{ t("main.loadError", { error: loadError }) }}</span>
        <button class="btn btn-red" @click="loadFleet">{{ t("common.retry") }}</button>
      </div>

      <!-- LOADING (skeleton) -->
      <div v-else-if="loadState === 'loading'" class="cards-wrap">
        <div class="cards-grid">
          <div class="fp-skel-card" v-for="n in 8" :key="n">
            <div class="fp-skel-line" style="width:40%"></div>
            <div class="fp-skel-line" style="width:70%"></div>
            <div class="fp-skel-line" style="width:55%"></div>
            <div class="fp-skel-line" style="width:80%"></div>
          </div>
        </div>
      </div>

      <!-- CARDS -->
      <div v-else-if="f.view === 'cards'" class="cards-wrap">
        <div v-if="!filtered.length" class="empty">
          <div class="empty-ic"><Icon :name="isScopeEmpty ? 'lock' : 'car'" :size="42" :stroke-width="1.5" /></div>
          <div>{{ isScopeEmpty ? t("main.noScope") : anyFilterActive ? t("main.noResultsFilters") : t("main.noVehicles") }}</div>
          <div v-if="!isScopeEmpty && activeFilterChips.length" class="fp-empty-filters">
            {{ t("main.activeFilters") }}
            <span class="fp-chip" v-for="(c, i) in activeFilterChips" :key="i">{{ c }}</span>
          </div>
          <button v-if="!isScopeEmpty && anyFilterActive" class="btn btn-blue" @click="resetFilters">{{ t("main.clearFilters") }}</button>
        </div>
        <div v-else class="cards-grid">
          <div
            v-for="v in filtered"
            :key="v.plate"
            class="vcard"
            :class="'vs-' + v.vehicle_status"
            @click="openPanel(v.plate)"
          >
            <div class="vc-top">
              <div><div class="vc-plate"><bdi>{{ v.plate }}</bdi></div></div>
              <div class="vc-icon-area">
                <span class="vc-sheet-icon"><Icon :name="icon(v)" :size="24" /></span>
                <span class="vc-fuel-badge">{{ trim(v.fuel) || "—" }}</span>
              </div>
            </div>
            <div class="vc-meta">
              <div class="vc-type">{{ v.vehicle_type || "—" }}</div>
              <div class="vc-office"><Icon name="building" :size="12" /> {{ v.rental_office }} &middot; {{ trim(v.project) || "—" }} &middot; <Icon name="pin" :size="12" /> {{ v.area }}</div>
            </div>
            <div class="vc-status-bar">
              <span class="sbadge" :class="sb(v).cls"><Icon :name="sb(v).ic" :size="13" />{{ sb(v).label }}</span>
              <span v-if="v.vehicle_status === 'workshop' && v.workshop_date" style="font-size:10px;color:var(--orange-l);font-family:'JetBrains Mono',monospace;display:inline-flex;align-items:center;gap:3px"><Icon name="calendar" :size="11" /> <bdi>{{ v.workshop_date }}</bdi></span>
              <span v-else-if="v.vehicle_status !== 'assigned' && v.vehicle_status !== 'workshop'" style="font-size:10px;color:var(--t3)">{{ t("card.prevDrivers", { n: v.history.length }) }}</span>
            </div>
            <!-- Fuel row (renders the "—" empty path; live API has no fuel rate) -->
            <div class="vc-fuel-row" @click.stop>
              <div>
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
                  <span class="fuel-grade-badge">{{ fuelView(v).gradeLabel }} · {{ fuelView(v).sarPerL }} {{ t("common.sarPerL") }}</span>
                </div>
                <div style="display:flex;align-items:baseline;gap:4px">
                  <span class="fuel-sar-val">{{ fuelView(v).sarDisplay }}</span>
                  <span class="fuel-sar-unit">{{ t("common.sar") }}</span>
                  <span class="fuel-sar-period">{{ t("common.perDay") }}</span>
                  <span v-if="fuelView(v).dailySAR > 0" class="fuel-monthly" style="margin-right:8px">· {{ fuelView(v).monDisplay }} {{ t("common.perMonthSuffix") }}</span>
                </div>
              </div>
            </div>
            <div v-if="v.vehicle_status === 'workshop'" class="vc-workshop-stripe"><Icon name="wrench" :size="13" /> {{ v.workshop_notes || t("card.inMaintenance") }}</div>
            <div v-if="v.vehicle_status === 'stolen'" class="vc-stolen-stripe"><Icon name="shield-alert" :size="13" /> {{ t("card.stolen") }} <template v-if="v.stolen_info && v.stolen_info.date">· <bdi>{{ v.stolen_info.date }}</bdi></template></div>
            <div v-if="(v.damages || []).length || (v.accidents || []).length" style="padding:3px 14px;display:flex;gap:6px;border-top:1px solid var(--b1)">
              <span v-if="(v.damages || []).length" style="font-size:10px;padding:2px 7px;background:var(--red-d);color:var(--red-l);border-radius:6px;border:1px solid rgba(220,38,38,.2);display:inline-flex;align-items:center;gap:3px"><Icon name="hammer" :size="11" /> {{ t("card.damageCount", { n: v.damages.length }) }}</span>
              <span v-if="(v.accidents || []).length" style="font-size:10px;padding:2px 7px;background:var(--amber-d);color:var(--amber-l);border-radius:6px;border:1px solid rgba(217,119,6,.2);display:inline-flex;align-items:center;gap:3px"><Icon name="crash" :size="11" /> {{ t("card.accidentCount", { n: v.accidents.length }) }}</span>
            </div>
            <div v-if="v.current_driver" class="vc-driver">
              <div class="drv-av">{{ initials(v.current_driver) }}</div>
              <div class="drv-info">
                <div class="drv-name">{{ v.current_driver.name_ar || v.current_driver.name_en || t("common.none") }}</div>
                <div class="drv-since">{{ t("card.since") }} <bdi>{{ v.current_driver.date_receive || t("common.none") }}</bdi> · {{ trim(v.current_driver.project) || t("common.none") }}</div>
              </div>
              <span class="lock-ico"><Icon name="lock" :size="15" /></span>
            </div>
            <div v-else class="no-driver">
              <template v-if="v.vehicle_status === 'available'"><Icon name="key" :size="14" /> {{ t("card.readyToAssign") }}</template>
              <template v-else-if="v.vehicle_status === 'workshop'"><Icon name="wrench" :size="14" /> {{ t("card.inMaintenance") }}</template>
              <template v-else><Icon name="circle-pause" :size="14" /> {{ t("card.outOfService") }}</template>
            </div>
            <div v-if="calcTotalDaysNum(v) > 0" class="vc-dur">
              <div class="dur-label">
                <span>{{ t("card.totalRunning", { n: calcTotalDaysNum(v) }) }}</span>
                <span><bdi>{{ v.history.length ? v.history[0].date_receive || "" : "" }}</bdi></span>
              </div>
              <div class="dur-bar"><div class="dur-fill" :style="{ width: Math.min(100, Math.round((calcTotalDaysNum(v) / 400) * 100)) + '%' }"></div></div>
            </div>
            <div class="vc-actions" @click.stop>
              <template v-if="v.vehicle_status === 'assigned'">
                <button class="ac ac-stop" :title="t('card.stopTitle')" @click="quickStop(v.plate)"><span class="ac-ico"><Icon name="circle-pause" :size="14" /></span>{{ t("card.stop") }}</button>
                <button class="ac ac-reassign" :title="t('card.reassignTitle')" @click="quickReassign(v.plate)"><span class="ac-ico"><Icon name="rotate-cw" :size="14" /></span>{{ t("card.reassign") }}</button>
                <button class="ac ac-workshop" :title="t('card.sendWorkshopAfterStopTitle')" @click="quickStop(v.plate, true)"><span class="ac-ico"><Icon name="wrench" :size="14" /></span>{{ t("card.workshop") }}</button>
              </template>
              <template v-else-if="v.vehicle_status === 'available'">
                <button class="ac ac-free" :title="t('card.assignNewTitle')" @click="quickReassign(v.plate)"><span class="ac-ico"><Icon name="key" :size="14" /></span>{{ t("card.assign") }}</button>
                <button class="ac ac-workshop" :title="t('card.sendWorkshopTitle')" @click="sendWorkshop(v.plate)"><span class="ac-ico"><Icon name="wrench" :size="14" /></span>{{ t("card.workshop") }}</button>
              </template>
              <template v-else-if="v.vehicle_status === 'workshop'">
                <button class="ac ac-free" :title="t('card.exitWorkshopTitle')" @click="exitWorkshop(v.plate)"><span class="ac-ico"><Icon name="circle-check" :size="14" /></span>{{ t("card.exit") }}</button>
                <button class="ac ac-reassign" :title="t('card.assignDirectTitle')" @click="quickReassign(v.plate)"><span class="ac-ico"><Icon name="key" :size="14" /></span>{{ t("card.assign") }}</button>
              </template>
              <template v-else>
                <button class="ac ac-free" :title="t('card.setAvailableTitle')" @click="setAvailable(v.plate)"><span class="ac-ico"><Icon name="circle-dot" :size="14" /></span>{{ t("card.available") }}</button>
                <button class="ac ac-workshop" :title="t('card.sendWorkshopTitle')" @click="sendWorkshop(v.plate)"><span class="ac-ico"><Icon name="wrench" :size="14" /></span>{{ t("card.workshop") }}</button>
              </template>
              <button v-if="v.vehicle_status === 'stolen'" class="ac" style="border-color:rgba(124,58,237,.25);color:var(--purple-l)" :title="t('card.recoverTitle')" @click="recoverVehicle(v.plate)"><span class="ac-ico"><Icon name="lock-open" :size="14" /></span>{{ t("card.recover") }}</button>
              <button v-else-if="v.vehicle_status === 'available'" class="ac" style="border-color:rgba(220,38,38,.25);color:var(--red-l)" :title="t('card.markStolenTitle')" @click="markStolen(v.plate)"><span class="ac-ico"><Icon name="shield-alert" :size="14" /></span>{{ t("card.markStolen") }}</button>
              <button class="ac ac-hist" :title="t('card.historyTitle')" @click="openPanel(v.plate, 5)"><span class="ac-ico"><Icon name="clipboard-list" :size="14" /></span><span class="hist-n">{{ v.history.length }}</span></button>
            </div>
          </div>
        </div>
      </div>

      <!-- TABLE -->
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th @click="onSortCol('sheet')">{{ t("table.colType") }}</th>
              <th @click="onSortCol('plate')">{{ t("table.colPlate") }}</th>
              <th @click="onSortCol('vehicle_type')">{{ t("table.colVehicle") }}</th>
              <th @click="onSortCol('rental_office')">{{ t("table.colOffice") }}</th>
              <th @click="onSortCol('vehicle_status')">{{ t("table.colStatus") }}</th>
              <th>{{ t("table.colCurrentDriver") }}</th>
              <th @click="onSortCol('project')">{{ t("table.colProject") }}</th>
              <th @click="onSortCol('area')">{{ t("table.colArea") }}</th>
              <th>{{ t("table.colDriverCount") }}</th>
              <th>{{ t("table.colRunningDays") }}</th>
              <th>{{ t("table.colAction") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filtered.length"><td colspan="11"><div class="empty"><div class="empty-ic"><Icon :name="isScopeEmpty ? 'lock' : 'search'" :size="42" :stroke-width="1.5" /></div>{{ isScopeEmpty ? t("main.noScope") : t("main.noResults") }}</div></td></tr>
            <tr v-for="v in filtered" :key="v.plate" @click="openPanel(v.plate)">
              <td><Icon :name="icon(v)" :size="18" /></td>
              <td><span class="mono" style="font-weight:700;color:var(--t1)"><bdi>{{ v.plate }}</bdi></span></td>
              <td>{{ v.vehicle_type }}</td>
              <td>{{ v.rental_office }}</td>
              <td><span class="sbadge" :class="sb(v).cls" style="display:inline-flex;gap:4px"><Icon :name="sb(v).ic" :size="12" />{{ sl(v.vehicle_status) }}</span></td>
              <td><template v-if="v.current_driver">{{ v.current_driver.name_ar || v.current_driver.name_en }} <Icon name="lock" :size="13" /></template><span v-else style="color:var(--t3)">—</span></td>
              <td>{{ trim(v.project) || t("common.none") }}</td>
              <td>{{ v.area }}</td>
              <td style="color:var(--purple-l)">{{ v.history.length }}</td>
              <td style="color:var(--amber-l);font-family:'JetBrains Mono',monospace">{{ calcTotalDaysNum(v) ? t("duration.dayUnit", { n: calcTotalDaysNum(v) }) : t("common.none") }}</td>
              <td @click.stop>
                <button class="btn" style="padding:3px 10px;font-size:11px" @click="openPanel(v.plate)">{{ t("table.details") }} <Icon name="chevron" :size="13" /></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- PANEL (right drawer) -->
  <transition name="fp-overlay">
    <div v-if="panel.open" class="panel-overlay open" @click.self="closePanel"></div>
  </transition>
  <transition name="fp-panel">
    <div v-if="panel.open && panel.vehicle" class="panel" style="display:flex">
      <div class="panel-head">
        <div class="ph-left">
          <div class="ph-plate"><bdi>{{ panel.vehicle.plate }}</bdi></div>
          <div class="ph-sub">{{ panel.vehicle.vehicle_type }} · {{ panel.vehicle.rental_office }} · <Icon :name="panel.vehicle.sheet === 'CAR' ? 'car' : 'bike'" :size="13" /> {{ panel.vehicle.sheet === "CAR" ? t("sheet.car") : t("sheet.bike") }}</div>
          <div class="ph-tags">
            <span class="tag">{{ trim(panel.vehicle.fuel) || t("common.none") }}</span>
            <span class="tag">{{ trim(panel.vehicle.project) || t("panel.noProject") }}</span>
            <span class="tag"><Icon name="pin" :size="11" /> {{ panel.vehicle.area }}</span>
            <span class="sbadge" :class="sb(panel.vehicle).cls" style="font-size:10px;display:inline-flex;gap:4px"><Icon :name="sb(panel.vehicle).ic" :size="11" />{{ sb(panel.vehicle).label }}</span>
          </div>
        </div>
        <button class="panel-close" @click="closePanel"><Icon name="x" :size="18" /></button>
      </div>
      <div class="panel-tabs" style="flex-wrap:wrap">
        <button class="ptab" :class="{ on: panel.tab === 0 }" @click="setPTab(0)"><Icon name="home" :size="14" /> {{ t("panel.overview") }}</button>
        <button class="ptab" :class="{ on: panel.tab === 1 }" @click="setPTab(1)"><Icon name="user" :size="14" /> {{ t("panel.driver") }}</button>
        <button class="ptab" :class="{ on: panel.tab === 2 }" @click="setPTab(2)"><Icon name="settings" :size="14" /> {{ t("panel.status") }}</button>
        <button class="ptab" :class="{ on: panel.tab === 3 }" @click="setPTab(3)"><Icon name="hammer" :size="14" /> {{ t("panel.damages") }}<span v-if="tabDmg" class="ptab-badge">{{ tabDmg }}</span></button>
        <button class="ptab" :class="{ on: panel.tab === 4 }" @click="setPTab(4)"><Icon name="crash" :size="14" /> {{ t("panel.accidents") }}<span v-if="tabAcc" class="ptab-badge" style="background:var(--amber-l)">{{ tabAcc }}</span></button>
        <button class="ptab" :class="{ on: panel.tab === 5 }" @click="setPTab(5)"><Icon name="clipboard-list" :size="14" /> {{ t("panel.log") }}</button>
      </div>
      <div class="panel-body">
        <!-- TAB 0: OVERVIEW -->
        <div v-if="panel.tab === 0" class="pb on">
          <div class="psect-title"><Icon name="chart-column" :size="14" /> {{ t("panel.vehicleStats") }}</div>
          <div class="pstats">
            <div class="pstat"><div class="pstat-n" style="color:var(--purple-l)">{{ panel.vehicle.history.length }}</div><div class="pstat-l">{{ t("panel.totalDrivers") }}</div></div>
            <div class="pstat"><div class="pstat-n" style="color:var(--amber-l)">{{ calcTotalDaysNum(panel.vehicle) }}</div><div class="pstat-l">{{ t("panel.runningDays") }}</div></div>
            <div class="pstat"><div class="pstat-n" style="color:var(--green-l)">{{ calcActiveDaysNum(panel.vehicle) }}</div><div class="pstat-l">{{ t("panel.activeDays") }}</div></div>
            <div class="pstat"><div class="pstat-n" style="color:var(--cyan-l)">{{ panel.vehicle.history.filter((h) => h.status === "Active").length }}</div><div class="pstat-l">{{ t("panel.activations") }}</div></div>
          </div>
          <div class="psect-title"><Icon name="search" :size="14" /> {{ t("panel.vehicleDetails") }}</div>
          <div class="kv-grid">
            <div class="kv"><div class="kv-l">{{ t("panel.plate") }}</div><div class="kv-v mono" style="font-size:16px;letter-spacing:2px"><bdi>{{ panel.vehicle.plate }}</bdi></div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.type") }}</div><div class="kv-v"><Icon :name="panel.vehicle.sheet === 'CAR' ? 'car' : 'bike'" :size="14" /> {{ panel.vehicle.sheet === "CAR" ? t("sheet.car") : t("sheet.bike") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.model") }}</div><div class="kv-v">{{ panel.vehicle.vehicle_type || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.fuel") }}</div><div class="kv-v">{{ panel.vehicle.fuel || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.rentalOffice") }}</div><div class="kv-v">{{ panel.vehicle.rental_office || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.area") }}</div><div class="kv-v">{{ panel.vehicle.area || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.project") }}</div><div class="kv-v">{{ trim(panel.vehicle.project) || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.vehicleStatus") }}</div><div class="kv-v">{{ sb(panel.vehicle).label }}</div></div>
          </div>
          <template v-if="panel.vehicle.current_driver">
            <div class="psect-title"><Icon name="user" :size="14" /> {{ t("panel.currentDriver") }}</div>
            <div class="cur-driver-card">
              <div class="cdc-av">{{ initials(panel.vehicle.current_driver) }}</div>
              <div class="cdc-info">
                <div class="cdc-name">{{ panel.vehicle.current_driver.name_ar || panel.vehicle.current_driver.name_en || t("common.none") }}</div>
                <div class="cdc-en">{{ panel.vehicle.current_driver.name_en || "" }}</div>
                <div class="cdc-chips">
                  <span class="cdc-chip"><Icon name="phone" :size="11" /> <bdi>{{ panel.vehicle.current_driver.mobile || t("common.none") }}</bdi></span>
                  <span class="cdc-chip"><Icon name="id-card" :size="11" /> <bdi>{{ panel.vehicle.current_driver.driver_id || t("common.none") }}</bdi></span>
                  <span class="cdc-chip"><Icon name="calendar" :size="11" /> <bdi>{{ panel.vehicle.current_driver.date_receive || t("common.none") }}</bdi></span>
                </div>
              </div>
              <span class="lock-pill"><Icon name="lock" :size="12" /> {{ t("panel.active") }}</span>
            </div>
          </template>
        </div>

        <!-- TAB 1: DRIVER -->
        <div v-else-if="panel.tab === 1" class="pb on">
          <template v-if="panel.vehicle.current_driver">
            <div class="alert alert-green"><Icon name="lock" :size="15" /> {{ t("driverTab.lockedFor", { name: panel.vehicle.current_driver.name_ar || panel.vehicle.current_driver.name_en }) }}</div>
            <div class="psect-title">{{ t("driverTab.currentDriverData") }}</div>
            <div class="kv-grid">
              <div class="kv"><div class="kv-l">{{ t("driverTab.nameAr") }}</div><div class="kv-v">{{ panel.vehicle.current_driver.name_ar || t("common.none") }}</div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.nameEn") }}</div><div class="kv-v">{{ panel.vehicle.current_driver.name_en || t("common.none") }}</div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.iqama") }}</div><div class="kv-v mono"><bdi>{{ panel.vehicle.current_driver.driver_id || t("common.none") }}</bdi></div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.mobile") }}</div><div class="kv-v mono"><bdi>{{ panel.vehicle.current_driver.mobile || t("common.none") }}</bdi></div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.project") }}</div><div class="kv-v">{{ trim(panel.vehicle.current_driver.project) || t("common.none") }}</div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.area") }}</div><div class="kv-v">{{ panel.vehicle.current_driver.area || t("common.none") }}</div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.receiveDate") }}</div><div class="kv-v mono"><bdi>{{ panel.vehicle.current_driver.date_receive || t("common.none") }}</bdi></div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.receiveBranch") }}</div><div class="kv-v">{{ panel.vehicle.current_driver.branch_receive || t("common.none") }}</div></div>
            </div>
            <div class="psect-title">{{ t("driverTab.actions") }}</div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-red" style="flex:1" @click="openStopForm"><Icon name="circle-pause" :size="15" /> {{ t("driverTab.stopAndLock") }}</button>
              <button class="btn btn-green" style="flex:1" @click="openReassignForm"><Icon name="rotate-cw" :size="15" /> {{ t("driverTab.reassignNew") }}</button>
            </div>
            <!-- Stop sub-form -->
            <div v-if="subForm === 'stop'" style="margin-top:14px;border:1px solid rgba(244,63,94,.2);border-radius:var(--r2);padding:14px;background:var(--red-d)">
              <div class="psect-title" style="color:var(--red-l)"><Icon name="circle-pause" :size="14" /> {{ t("stopForm.title") }}</div>
              <div class="form-grid" style="margin-bottom:10px">
                <div class="ff"><div class="fl">{{ t("stopForm.deliverDate") }} *</div><input class="fi" type="date" v-model="sf.date" /></div>
                <div class="ff"><div class="fl">{{ t("stopForm.deliverBranch") }}</div><input class="fi" v-model="sf.branch" :placeholder="t('stopForm.branchPlaceholder')" /></div>
                <div class="ff"><div class="fl">{{ t("stopForm.stopReason") }}</div>
                  <select class="fsel" v-model="sf.reason">
                    <option value="">{{ t("stopForm.chooseReason") }}</option>
                    <option :value="t('stopForm.reasonContractEnd')">{{ t("stopForm.reasonContractEnd") }}</option>
                    <option :value="t('stopForm.reasonTransfer')">{{ t("stopForm.reasonTransfer") }}</option>
                    <option :value="t('stopForm.reasonProjectStopped')">{{ t("stopForm.reasonProjectStopped") }}</option>
                    <option :value="t('stopForm.reasonVehicleFault')">{{ t("stopForm.reasonVehicleFault") }}</option>
                    <option :value="t('stopForm.reasonDriverRequest')">{{ t("stopForm.reasonDriverRequest") }}</option>
                    <option :value="t('stopForm.reasonViolation')">{{ t("stopForm.reasonViolation") }}</option>
                    <option :value="t('stopForm.reasonOther')">{{ t("stopForm.reasonOther") }}</option>
                  </select>
                </div>
                <div class="ff"><div class="fl">{{ t("stopForm.nextStatus") }}</div>
                  <select class="fsel" v-model="sf.nextStatus">
                    <option value="available">{{ t("stopForm.nextAvailable") }}</option>
                    <option value="workshop">{{ t("stopForm.nextWorkshop") }}</option>
                    <option value="stopped">{{ t("stopForm.nextStopped") }}</option>
                  </select>
                </div>
              </div>
              <div class="ff"><div class="fl">{{ t("stopForm.notes") }}</div><textarea class="fta" v-model="sf.notes" :placeholder="t('stopForm.notesPlaceholder')"></textarea></div>
              <div class="form-actions" style="margin-top:10px">
                <button class="btn" @click="subForm = null">{{ t("common.cancel") }}</button>
                <button class="btn btn-red" @click="confirmStop"><Icon name="circle-pause" :size="15" /> {{ t("stopForm.confirm") }}</button>
              </div>
            </div>
            <!-- Reassign sub-form -->
            <div v-if="subForm === 'reassign'" style="margin-top:14px;border:1px solid rgba(0,201,122,.2);border-radius:var(--r2);padding:14px;background:var(--green-d)">
              <div class="psect-title" style="color:var(--green-l)"><Icon name="rotate-cw" :size="14" /> {{ t("reassignForm.title") }}</div>
              <div class="alert alert-amber" style="margin-bottom:12px"><Icon name="triangle-alert" :size="15" /> {{ t("reassignForm.autoLockHint", { name: panel.vehicle.current_driver.name_ar || panel.vehicle.current_driver.name_en || t("common.none") }) }}</div>
              <div class="psect-title" style="color:var(--green-l);margin-top:12px">{{ t("reassignForm.newDriverData") }}</div>
              <div class="form-grid">
                <div class="ff"><div class="fl">{{ t("reassignForm.nameAr") }} *</div><input class="fi" v-model="rf.nameAr" :placeholder="t('reassignForm.nameArPlaceholder')" /></div>
                <div class="ff"><div class="fl">{{ t("reassignForm.nameEn") }}</div><input class="fi" v-model="rf.nameEn" :placeholder="t('reassignForm.nameEnPlaceholder')" /></div>
                <div class="ff"><div class="fl">{{ t("reassignForm.iqama") }} *</div><input class="fi mono" v-model="rf.iqama" placeholder="2XXXXXXXXX" /></div>
                <div class="ff"><div class="fl">{{ t("reassignForm.mobile") }} *</div><input class="fi" v-model="rf.mobile" placeholder="05XXXXXXXX" /></div>
                <div class="ff"><div class="fl">{{ t("reassignForm.project") }}</div>
                  <select class="fsel" v-model="rf.project"><option>KEETA</option><option>SHIPMENT</option><option>KEEMART</option><option>NINJA</option><option>NOON</option><option>ARAMEX</option></select>
                </div>
                <div class="ff"><div class="fl">{{ t("reassignForm.area") }}</div>
                  <select class="fsel" v-model="rf.area"><option>RIYADH</option><option>JADAH</option><option>MAKA</option><option>DAMAM</option><option>TAIF</option></select>
                </div>
                <div class="ff"><div class="fl">{{ t("reassignForm.receiveDate") }}</div><input class="fi" type="date" v-model="rf.date" /></div>
                <div class="ff"><div class="fl">{{ t("reassignForm.receiveBranch") }}</div><input class="fi" v-model="rf.branch" :placeholder="t('reassignForm.branchPlaceholder')" /></div>
              </div>
              <div class="form-actions" style="margin-top:12px">
                <button class="btn" @click="subForm = null">{{ t("common.cancel") }}</button>
                <button class="btn btn-green" @click="submitReassign"><Icon name="lock" :size="15" /> {{ t("reassignForm.assignAndLock") }}</button>
              </div>
            </div>
          </template>
          <template v-else>
            <div v-if="panel.vehicle.vehicle_status === 'workshop'" class="alert alert-orange"><Icon name="wrench" :size="15" /> {{ t("driverTab.inWorkshopHint") }}</div>
            <div v-if="panel.vehicle.vehicle_status === 'stopped'" class="alert alert-amber"><Icon name="circle-pause" :size="15" /> {{ t("driverTab.stoppedHint") }}</div>
            <div class="psect-title">{{ t("driverTab.assignNewDriver") }}</div>
            <div class="form-grid">
              <div class="ff"><div class="fl">{{ t("reassignForm.nameAr") }} *</div><input class="fi" v-model="rf.nameAr" :placeholder="t('reassignForm.nameArPlaceholder')" /></div>
              <div class="ff"><div class="fl">{{ t("reassignForm.nameEn") }}</div><input class="fi" v-model="rf.nameEn" :placeholder="t('reassignForm.nameEnPlaceholder')" /></div>
              <div class="ff"><div class="fl">{{ t("reassignForm.iqama") }} *</div><input class="fi mono" v-model="rf.iqama" placeholder="2XXXXXXXXX" /></div>
              <div class="ff"><div class="fl">{{ t("reassignForm.mobile") }} *</div><input class="fi" v-model="rf.mobile" placeholder="05XXXXXXXX" /></div>
              <div class="ff"><div class="fl">{{ t("reassignForm.project") }}</div>
                <select class="fsel" v-model="rf.project"><option>KEETA</option><option>SHIPMENT</option><option>KEEMART</option><option>NINJA</option><option>NOON</option><option>ARAMEX</option></select>
              </div>
              <div class="ff"><div class="fl">{{ t("reassignForm.area") }}</div>
                <select class="fsel" v-model="rf.area"><option>RIYADH</option><option>JADAH</option><option>MAKA</option><option>DAMAM</option><option>TAIF</option></select>
              </div>
              <div class="ff"><div class="fl">{{ t("reassignForm.receiveDate") }}</div><input class="fi" type="date" v-model="rf.date" /></div>
              <div class="ff"><div class="fl">{{ t("reassignForm.receiveBranch") }}</div><input class="fi" v-model="rf.branch" :placeholder="t('reassignForm.branchPlaceholder')" /></div>
            </div>
            <div class="form-actions" style="margin-top:12px">
              <button class="btn btn-green" @click="submitReassign"><Icon name="lock" :size="15" /> {{ t("reassignForm.assignAndLock") }}</button>
            </div>
          </template>
        </div>

        <!-- TAB 2: STATUS -->
        <div v-else-if="panel.tab === 2" class="pb on">
          <div class="psect-title">{{ t("statusTab.title") }}</div>
          <div class="status-grid">
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'assigned' ? 'cur-assigned' : ''" @click="changeStatus(panel.vehicle.plate, 'assigned')">
              <span class="sp-ico"><Icon name="lock" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'assigned' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.assignedLabel") }}</span><span class="sp-desc">{{ t("statusTab.assignedDesc") }}</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'available' ? 'cur-available' : ''" @click="changeStatus(panel.vehicle.plate, 'available')">
              <span class="sp-ico"><Icon name="key" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'available' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.availableLabel") }}</span><span class="sp-desc">{{ t("statusTab.availableDesc") }}</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'workshop' ? 'cur-workshop' : ''" @click="changeStatus(panel.vehicle.plate, 'workshop')">
              <span class="sp-ico"><Icon name="wrench" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'workshop' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.workshopLabel") }}</span><span class="sp-desc">{{ t("statusTab.workshopDesc") }}</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'stopped' ? 'cur-stopped' : ''" @click="changeStatus(panel.vehicle.plate, 'stopped')">
              <span class="sp-ico"><Icon name="circle-pause" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'stopped' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.stoppedLabel") }}</span><span class="sp-desc">{{ t("statusTab.stoppedDesc") }}</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'stolen' ? 'cur-stopped' : ''" @click="changeStatus(panel.vehicle.plate, 'stolen')">
              <span class="sp-ico"><Icon name="shield-alert" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'stolen' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.stolenLabel") }}</span><span class="sp-desc">{{ t("statusTab.stolenDesc") }}</span>
            </button>
          </div>
          <template v-if="panel.vehicle.vehicle_status === 'workshop'">
            <button class="btn btn-green" style="width:100%;justify-content:center" @click="changeStatus(panel.vehicle.plate, 'available')"><Icon name="circle-check" :size="15" /> {{ t("statusTab.exitWorkshop") }}</button>
          </template>
          <template v-if="panel.vehicle.vehicle_status === 'stolen'">
            <button class="btn btn-green" style="width:100%;justify-content:center;margin-top:8px" @click="recoverVehicle(panel.vehicle.plate)"><Icon name="lock-open" :size="15" /> {{ t("statusTab.recoverVehicle") }}</button>
          </template>
          <template v-if="panel.vehicle.vehicle_status === 'available' || panel.vehicle.vehicle_status === 'stopped'">
            <div class="psect-title" style="color:var(--red-l)"><Icon name="shield-alert" :size="14" /> {{ t("statusTab.reportTheft") }}</div>
            <button class="btn btn-red" style="width:100%;justify-content:center" @click="openStolenForm"><Icon name="shield-alert" :size="15" /> {{ t("statusTab.reportTheftBtn") }}</button>
            <div v-if="subForm === 'stolen'" style="border:1px solid rgba(124,58,237,.2);border-radius:var(--r2);padding:14px;background:var(--purple-d);margin-top:10px">
              <div class="psect-title" style="color:var(--purple-l)"><Icon name="shield-alert" :size="14" /> {{ t("stolenForm.title") }}</div>
              <div class="form-grid">
                <div class="ff"><div class="fl">{{ t("stolenForm.theftDate") }} *</div><input class="fi" type="date" v-model="stf.date" /></div>
                <div class="ff"><div class="fl">{{ t("stolenForm.policeNumber") }}</div><input class="fi mono" v-model="stf.police" :placeholder="t('stolenForm.policePlaceholder')" /></div>
                <div class="ff"><div class="fl">{{ t("stolenForm.location") }}</div><input class="fi" v-model="stf.location" :placeholder="t('stolenForm.locationPlaceholder')" /></div>
                <div class="ff"><div class="fl">{{ t("stolenForm.reportedBy") }}</div><input class="fi" v-model="stf.reporter" :placeholder="t('stolenForm.reporterPlaceholder')" /></div>
                <div class="ff" style="grid-column:1/-1"><div class="fl">{{ t("stolenForm.details") }}</div><textarea class="fta" v-model="stf.desc" :placeholder="t('stolenForm.detailsPlaceholder')"></textarea></div>
                <div class="ff" style="grid-column:1/-1"><div class="fl">{{ t("stolenForm.extraNotes") }}</div><textarea class="fta" v-model="stf.notes"></textarea></div>
              </div>
              <div class="form-actions" style="margin-top:10px">
                <button class="btn" @click="subForm = null">{{ t("common.cancel") }}</button>
                <button class="btn" style="background:var(--purple);color:#fff;border-color:var(--purple)" @click="submitStolen"><Icon name="shield-alert" :size="15" /> {{ t("stolenForm.confirm") }}</button>
              </div>
            </div>
          </template>
        </div>

        <!-- TAB 3: DAMAGES (live API has none → empty state) -->
        <div v-else-if="panel.tab === 3" class="pb on">
          <div class="psect-title"><Icon name="hammer" :size="14" /> {{ t("damages.title") }}</div>
          <div v-if="!(panel.vehicle.damages || []).length" class="empty"><div class="empty-ic"><Icon name="hammer" :size="42" :stroke-width="1.5" /></div><div>{{ t("damages.empty") }}</div></div>
          <div v-for="(d, i) in panel.vehicle.damages || []" :key="i" class="incident-card">
            <div class="incident-card-head">
              <div style="display:flex;align-items:center;gap:8px">
                <span class="incident-badge" :class="d.status === 'completed' ? 'incident-badge-ok' : ''"><Icon :name="d.status === 'completed' ? 'circle-check' : 'hammer'" :size="12" />{{ d.status === "completed" ? t("damages.repaired") : t("damages.damage") }}</span>
                <span style="font-size:12px;font-weight:600;color:var(--t1)"><bdi>{{ d.date || t("common.none") }}</bdi></span>
              </div>
              <div style="display:flex;gap:6px"><span v-if="d.cost" style="font-size:11px;color:var(--amber-l);font-weight:600;display:inline-flex;align-items:center;gap:3px"><Icon name="banknote" :size="12" /> {{ d.cost }} {{ t("common.sar") }}</span></div>
            </div>
            <div class="incident-card-body">
              <div class="inc-row"><span class="inc-label">{{ t("damages.description") }}</span>{{ d.description || t("common.none") }}</div>
            </div>
          </div>
        </div>

        <!-- TAB 4: ACCIDENTS (live API has none → empty state) -->
        <div v-else-if="panel.tab === 4" class="pb on">
          <div class="psect-title"><Icon name="crash" :size="14" /> {{ t("accidents.title") }}</div>
          <div v-if="!(panel.vehicle.accidents || []).length" class="empty"><div class="empty-ic"><Icon name="crash" :size="42" :stroke-width="1.5" /></div><div>{{ t("accidents.empty") }}</div></div>
          <div v-for="(a, i) in panel.vehicle.accidents || []" :key="i" class="incident-card">
            <div class="incident-card-head">
              <div style="display:flex;align-items:center;gap:8px">
                <span class="incident-badge incident-badge-acc" :class="a.status === 'closed' ? 'incident-badge-ok' : ''"><Icon :name="a.status === 'closed' ? 'circle-check' : 'crash'" :size="12" />{{ a.status === "closed" ? t("accidents.closed") : t("accidents.accident") }}</span>
                <span style="font-size:12px;font-weight:600;color:var(--t1)"><bdi>{{ a.date || t("common.none") }}</bdi></span>
              </div>
            </div>
            <div class="incident-card-body">
              <div class="inc-row"><span class="inc-label">{{ t("accidents.description") }}</span>{{ a.description || t("common.none") }}</div>
            </div>
          </div>
        </div>

        <!-- TAB 5: LOG -->
        <div v-else-if="panel.tab === 5" class="pb on">
          <div v-if="!panel.vehicle.history.length" class="empty"><div class="empty-ic"><Icon name="clipboard-list" :size="42" :stroke-width="1.5" /></div><div>{{ t("logTab.empty") }}</div></div>
          <template v-else>
            <div class="psect-title">{{ t("logTab.fullTimeline", { n: panel.vehicle.history.length }) }}</div>
            <div class="tl">
              <div v-for="(item, i) in historyItems(panel.vehicle)" :key="i" class="tl-item">
                <div class="tl-ic" :class="item.d.status === 'Active' ? 'ti-active' : 'ti-stopped'"><Icon name="user" :size="15" /></div>
                <div class="tl-info">
                  <div class="tl-head">
                    {{ item.d.name_ar || item.d.name_en || t("logTab.driver") }}
                    <span class="tl-status" :class="item.d.status === 'Active' ? 'tls-active' : 'tls-stopped'"><Icon :name="item.d.status === 'Active' ? 'circle-check' : 'circle-pause'" :size="11" />{{ item.d.status === "Active" ? t("logTab.active") : t("logTab.ended") }}</span>
                  </div>
                  <div class="tl-sub">{{ item.d.name_en || "" }} · <Icon name="phone" :size="11" /> <bdi>{{ item.d.mobile || t("common.none") }}</bdi> · <Icon name="id-card" :size="11" /> <bdi>{{ item.d.driver_id || t("common.none") }}</bdi></div>
                  <div class="tl-sub"><Icon name="package" :size="11" /> {{ trim(item.d.project) || t("common.none") }} · <Icon name="pin" :size="11" /> {{ item.d.area || t("common.none") }} · <Icon name="building" :size="11" /> {{ item.d.branch_receive || t("common.none") }}</div>
                  <span class="tl-dates"><bdi>{{ item.d.date_receive || t("common.none") }}</bdi> → <bdi>{{ item.d.date_deliver || (item.d.status === "Active" ? t("common.ongoing") : t("common.none")) }}</bdi></span>
                  <span v-if="calcDur(item.d.date_receive, item.d.date_deliver || (item.d.status === 'Active' ? today() : ''))" class="tl-dur">{{ calcDur(item.d.date_receive, item.d.date_deliver || (item.d.status === "Active" ? today() : "")) }}</span>
                  <div v-if="item.d.reason" class="tl-reason">{{ t("logTab.reason", { v: item.d.reason }) }}</div>
                  <div v-if="item.d.notes" class="tl-note">{{ t("logTab.note", { v: item.d.notes }) }}</div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </transition>

  <!-- TOAST -->
  <div class="toast" :class="[toast.show ? 'show' : '', 'toast-' + toast.type]">{{ toast.msg }}</div>

  <!-- CUSTOM CONFIRM MODAL -->
  <div v-if="cf.open" class="cf-overlay" @click.self="cfDo(false)">
    <div class="cf-box">
      <div class="cf-icon"><Icon :name="cf.icon" :size="36" :stroke-width="1.75" /></div>
      <div class="cf-title">{{ cf.title }}</div>
      <div class="cf-msg">{{ cf.msg }}</div>
      <div class="cf-btns">
        <button class="btn" @click="cfDo(false)">{{ t("common.cancel") }}</button>
        <button class="btn" :class="cf.okCls" @click="cfDo(true)">{{ cf.okLabel }}</button>
      </div>
    </div>
  </div>
</template>
