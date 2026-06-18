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
import { ref, reactive, computed, onMounted } from "vue";
import { call } from "./api.js";
import Icon from "./components/Icon.vue";

// ═══════════ DATA ═══════════
const vehicles = ref([]);
const loadState = ref("loading"); // loading | ready | error
const loadError = ref("");

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
  if (days > 365) return Math.round(days / 30) + " شهر";
  return days + " يوم";
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

// Status badge meta (his SB map). `ic` is the Lucide icon name rendered in the
// badge; the label is plain text so it translates cleanly.
const SB = {
  assigned: { cls: "sb-assigned", label: "مُسند لسائق", ic: "lock" },
  available: { cls: "sb-available", label: "متاح في المكتب", ic: "circle-dot" },
  workshop: { cls: "sb-workshop", label: "في الورشة", ic: "wrench" },
  stopped: { cls: "sb-stopped", label: "متوقف", ic: "circle-pause" },
  stolen: { cls: "sb-stolen", label: "مسروق", ic: "shield-alert" },
};
const sb = (v) => SB[v.vehicle_status] || SB.stopped;
// Table short labels (his SL map) — plain text; the icon renders alongside.
const SL = {
  assigned: "مُسند",
  available: "متاح",
  workshop: "ورشة",
  stopped: "متوقف",
  stolen: "مسروق",
};
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
  const labels = { receive: "الاستلام", deliver: "التسليم", any: "أي تاريخ" };
  return `${filtered.value.length} مركبة · فلتر ${labels[f.dateType]}: ${
    f.dateFrom || "…"
  } → ${f.dateTo || "اليوم"}`;
});

// Enriched empty-state chips describing which filters are active.
const activeFilterChips = computed(() => {
  const c = [];
  if (f.search) c.push(`بحث: ${f.search}`);
  if (f.status) c.push(`الحالة: ${SB[f.status]?.label || f.status}`);
  if (f.sheet) c.push(`النوع: ${f.sheet}`);
  if (f.fuel) c.push(`الوقود: ${f.fuel}`);
  if (f.project) c.push(`المشروع: ${f.project}`);
  if (f.area) c.push(`المنطقة: ${f.area}`);
  if (f.office) c.push(`المكتب: ${f.office}`);
  if (f.dateFrom || f.dateTo)
    c.push(`التاريخ: ${f.dateFrom || "…"} → ${f.dateTo || "اليوم"}`);
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
  okLabel: "تأكيد",
  okCls: "btn-blue",
});
let cfResolve = null;
function cfShow(title, msg, icon = "triangle-alert", okLabel = "تأكيد", okCls = "btn-blue") {
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
    showToast("الاسم ورقم الإقامة مطلوبان", "amber");
    return;
  }
  const ok = await cfShow(
    "تأكيد تخصيص السائق",
    `تخصيص "${trim(rf.nameAr)}" للمركبة ${v.plate}؟`,
    "lock",
    "تخصيص",
    "btn-green"
  );
  if (!ok) return;
  try {
    await call(POST("reassign"), {
      type: "POST",
      args: { plate: v.plate, driver_id: trim(rf.iqama), date: rf.date || today() },
    });
    showToast(`تم قفل الملف وتخصيص ${trim(rf.nameAr)} للمركبة ${v.plate}`, "green");
    subForm.value = null;
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}

// Stop sub-form model. nextStatus mirrors his "الحالة بعد الإيقاف": after the
// stop, optionally chain workshop_in / recover so the live state matches.
const sf = reactive({ date: today(), branch: "", reason: "", notes: "", nextStatus: "available" });
function openStopForm() {
  Object.assign(sf, { date: today(), branch: "", reason: "", notes: "", nextStatus: "available" });
  subForm.value = "stop";
}
async function confirmStop() {
  const v = panel.vehicle;
  if (!v || !v.current_driver) return;
  const drName = v.current_driver.name_ar || v.current_driver.name_en || "السائق";
  const ok = await cfShow(
    "إيقاف السائق",
    `إيقاف "${drName}" عن المركبة ${v.plate}؟`,
    "circle-pause",
    "تأكيد الإيقاف",
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
      sf.nextStatus === "available" ? "متاحة" : sf.nextStatus === "workshop" ? "في الورشة" : "متوقفة";
    showToast(`تم إيقاف السائق — المركبة ${label}`, "green");
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
    "تسجيل بلاغ سرقة",
    `تسجيل سرقة المركبة ${v.plate}؟\nهذا الإجراء لا يمكن التراجع عنه بسهولة.`,
    "shield-alert",
    "تأكيد التسجيل",
    "btn-red"
  );
  if (!ok) return;
  try {
    await call(POST("report_theft"), {
      type: "POST",
      args: { plate: v.plate, location: trim(stf.location), report_number: trim(stf.police) },
    });
    showToast("تم تسجيل بلاغ السرقة", "amber");
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
    showToast("أوقف السائق أولاً قبل الإرسال للورشة", "amber");
    return;
  }
  const ok = await cfShow("إرسال للورشة", `إرسال المركبة ${plate} للورشة؟`, "wrench", "إرسال", "btn-amber");
  if (!ok) return;
  try {
    await call(POST("workshop_in"), { type: "POST", args: { plate } });
    showToast("تم إرسال المركبة للورشة", "amber");
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}
async function exitWorkshop(plate) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  const ok = await cfShow(
    "خروج من الورشة",
    `تأكيد خروج المركبة ${plate} من الورشة؟\nسيتم تعيينها كمتاحة.`,
    "circle-check",
    "تأكيد الخروج",
    "btn-green"
  );
  if (!ok) return;
  try {
    await call(POST("workshop_out"), { type: "POST", args: { plate } });
    showToast("خروج من الورشة — المركبة متاحة", "green");
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}
async function setAvailable(plate) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  const ok = await cfShow("تعيين كمتاح", `تعيين المركبة ${plate} كمتاحة في المكتب؟`, "circle-dot", "تأكيد", "btn-blue");
  if (!ok) return;
  try {
    await call(POST("recover"), { type: "POST", args: { plate } });
    showToast("المركبة متاحة في المكتب", "green");
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}
async function recoverVehicle(plate) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  const ok = await cfShow(
    "استرداد المركبة",
    `استرداد المركبة ${plate}\nوتعيينها كمتاحة؟`,
    "lock-open",
    "تأكيد الاسترداد",
    "btn-green"
  );
  if (!ok) return;
  try {
    await call(POST("recover"), { type: "POST", args: { plate } });
    showToast("تم استرداد المركبة — متاحة الآن", "green");
    await reloadFleet();
  } catch (e) {
    showToast(serverMsg(e), "red");
  }
}
function markStolen(plate) {
  openPanel(plate, 2);
  openStolenForm();
}

// Status-picker grid in the panel "الحالة" tab → routes to the right endpoint.
async function changeStatus(plate, newStatus) {
  const v = vehicles.value.find((x) => x.plate === plate);
  if (!v) return;
  if (newStatus === v.vehicle_status) return;
  if (newStatus === "assigned" && !v.current_driver) {
    showToast("لا يوجد سائق — خصص سائقاً أولاً", "amber");
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
    showToast("أوقف السائق الحالي أولاً", "amber");
    return;
  }
  if (newStatus === "stolen") {
    openStolenForm();
    return;
  }
  const labels = { assigned: "مُسند", available: "متاح", workshop: "في الورشة", stopped: "متوقف" };
  const icons = { assigned: "lock", available: "circle-dot", workshop: "wrench", stopped: "circle-pause" };
  const ok = await cfShow(
    "تغيير حالة المركبة",
    `تغيير حالة ${plate}\nمن: ${labels[v.vehicle_status] || v.vehicle_status}\nإلى: ${labels[newStatus] || newStatus}`,
    icons[newStatus] || "triangle-alert",
    "تأكيد التغيير",
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
    showToast("تم تحديث حالة المركبة", "green");
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
  const gradeLabel = grade === "DIESEL" ? "ديزل" : grade === "95" ? "بنزين 95" : "بنزين 91";
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
        <div class="brand-name">Fleet OS</div>
      </div>
    </div>
    <div class="search-bar">
      <span class="si"><Icon name="search" :size="15" /></span>
      <input v-model="f.search" placeholder="ابحث: لوحة، سائق، نوع، مكتب..." />
    </div>
    <div class="status-pills">
      <span class="sp sp-all" :class="{ active: f.status === '' }" @click="setSP('')">{{ counts.total }} كل المركبات</span>
      <span class="sp sp-assigned" :class="{ active: f.status === 'assigned' }" @click="setSP('assigned')">{{ counts.assigned }} مُسند</span>
      <span class="sp sp-available" :class="{ active: f.status === 'available' }" @click="setSP('available')">{{ counts.available }} متاح</span>
      <span class="sp sp-workshop" :class="{ active: f.status === 'workshop' }" @click="setSP('workshop')">{{ counts.workshop }} ورشة</span>
      <span class="sp sp-stopped" :class="{ active: f.status === 'stopped' }" @click="setSP('stopped')">{{ counts.stopped }} متوقف</span>
      <span class="sp sp-stolen" :class="{ active: f.status === 'stolen' }" @click="setSP('stolen')">{{ counts.stolen }} مسروق</span>
    </div>
  </div>

  <div class="layout">
    <!-- SIDEBAR -->
    <div class="sidebar">
      <div class="sidebar-header"><span class="sidebar-title"><Icon name="funnel" :size="13" /> الفلاتر والإحصائيات</span></div>
      <div class="sidebar-scroll">
        <div class="fg">
          <div class="fl">نوع المركبة</div>
          <div class="fchips">
            <button class="fchip" :class="{ on: f.sheet === '' }" @click="setSheet('')">الكل</button>
            <button class="fchip" :class="{ on: f.sheet === 'CAR' }" @click="setSheet('CAR')"><Icon name="car" :size="15" /> سيارات</button>
            <button class="fchip" :class="{ on: f.sheet === 'MOTORCYCLE' }" @click="setSheet('MOTORCYCLE')"><Icon name="bike" :size="15" /> دبابات</button>
          </div>
        </div>
        <div class="fg">
          <div class="fl">المشروع</div>
          <select class="fs" v-model="f.project">
            <option value="">الكل</option>
            <option>KEETA</option><option>KEEMART</option><option>SHIPMENT</option>
            <option>NINJA</option><option>NOON</option><option>ARAMEX</option>
            <option>STARLINKS</option>
            <option>NINJA-DIEANA</option>
          </select>
        </div>
        <div class="fg">
          <div class="fl">المنطقة</div>
          <select class="fs" v-model="f.area">
            <option value="">الكل</option>
            <option>RIYADH</option><option>JADAH</option><option>MAKA</option>
            <option>DAMAM</option><option>TAIF</option><option>MAJMA</option>
            <option>KHARJ</option><option>YANBU</option>
          </select>
        </div>
        <div class="fg">
          <div class="fl">مكتب الإيجار</div>
          <select class="fs" v-model="f.office">
            <option value="">الكل</option>
            <option>AFMCO</option><option>SAFI - T</option><option>SAFI - R</option>
            <option>WASEL</option><option>TRAFEL</option>
          </select>
        </div>
        <div class="fg">
          <div class="fl">الوقود</div>
          <div class="fchips">
            <button class="fchip" :class="{ on: f.fuel === '' }" @click="setFuel('')">الكل</button>
            <button class="fchip" :class="{ on: f.fuel === 'PETROL' }" @click="setFuel('PETROL')"><Icon name="fuel" :size="15" /> بترول</button>
            <button class="fchip" :class="{ on: f.fuel === 'DESIL' }" @click="setFuel('DESIL')"><Icon name="fuel" :size="15" /> ديزل</button>
          </div>
        </div>
        <div class="sep"></div>
        <div class="fg">
          <div class="fl"><Icon name="calendar" :size="13" /> نوع بحث التاريخ</div>
          <div class="fchips">
            <button class="fchip" :class="{ on: f.dateType === 'receive' }" @click="setDateType('receive')">الاستلام</button>
            <button class="fchip" :class="{ on: f.dateType === 'deliver' }" @click="setDateType('deliver')">التسليم</button>
            <button class="fchip" :class="{ on: f.dateType === 'any' }" @click="setDateType('any')">أي تاريخ</button>
          </div>
        </div>
        <div class="fg">
          <div class="fl">من تاريخ</div>
          <input type="date" class="fs" v-model="f.dateFrom" />
        </div>
        <div class="fg">
          <div class="fl">إلى تاريخ</div>
          <input type="date" class="fs" v-model="f.dateTo" />
        </div>
        <div class="fg">
          <div class="fl">فترة سريعة</div>
          <div class="fchips" style="flex-wrap:wrap">
            <button class="fchip" @click="setQuickDate(7)">7 أيام</button>
            <button class="fchip" @click="setQuickDate(30)">شهر</button>
            <button class="fchip" @click="setQuickDate(90)">3 أشهر</button>
            <button class="fchip" @click="setQuickDate(180)">6 أشهر</button>
            <button class="fchip" @click="setQuickDate(365)">سنة</button>
            <button class="fchip" @click="clearDateFilter">مسح</button>
          </div>
        </div>
        <div v-if="hasDateFilter" style="font-size:10px;color:var(--t3);padding:4px 0">{{ dateInfo }}</div>
        <div class="sep"></div>
        <button class="btn" style="width:100%;justify-content:center" @click="resetFilters"><Icon name="rotate-cw" :size="15" /> إعادة تعيين</button>
        <div class="sep"></div>
        <div class="fl" style="margin-bottom:8px"><Icon name="chart-column" :size="13" /> إحصائيات سريعة</div>
        <div class="stat-mini-grid">
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--blue-l)">{{ counts.total }}</div><div class="stat-mini-l">إجمالي</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--green-l)">{{ counts.assigned }}</div><div class="stat-mini-l">مُسند</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--cyan-l)">{{ counts.available }}</div><div class="stat-mini-l">متاح</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--orange-l)">{{ counts.workshop }}</div><div class="stat-mini-l">ورشة</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--t3)">{{ counts.stopped }}</div><div class="stat-mini-l">متوقف</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--purple-l)">{{ counts.stolen }}</div><div class="stat-mini-l">مسروق</div></div>
          <div class="stat-mini"><div class="stat-mini-n" style="color:var(--blue-l)">{{ counts.drivers }}</div><div class="stat-mini-l">سائق</div></div>
        </div>
      </div>
    </div>

    <!-- MAIN -->
    <div class="main">
      <div class="main-header">
        <div style="display:flex;align-items:center;gap:10px">
          <span class="rcount">{{ filtered.length }} مركبة</span>
          <select class="fs" style="width:auto;font-size:11px" v-model="f.sort">
            <option value="plate">ترتيب: اللوحة</option>
            <option value="status">ترتيب: الحالة</option>
            <option value="vehicle_type">ترتيب: النوع</option>
            <option value="drivers_desc">ترتيب: الأكثر سائقين</option>
            <option value="duration_desc">ترتيب: الأطول تشغيلاً</option>
          </select>
        </div>
        <div class="view-tabs">
          <button class="vt" :class="{ on: f.view === 'cards' }" @click="setView('cards')"><Icon name="layout-grid" :size="14" /> كروت</button>
          <button class="vt" :class="{ on: f.view === 'table' }" @click="setView('table')"><Icon name="list" :size="14" /> جدول</button>
        </div>
      </div>

      <!-- ERROR (persistent banner + retry) -->
      <div v-if="loadState === 'error'" class="fp-error-banner">
        <span style="color:var(--red-l)"><Icon name="triangle-alert" :size="20" /></span>
        <span class="fp-err-msg">تعذّر تحميل بيانات الأسطول: {{ loadError }}</span>
        <button class="btn btn-red" @click="loadFleet">إعادة المحاولة</button>
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
          <div class="empty-ic"><Icon name="car" :size="42" :stroke-width="1.5" /></div>
          <div>{{ anyFilterActive ? "لا نتائج مطابقة للفلاتر" : "لا توجد مركبات" }}</div>
          <div v-if="activeFilterChips.length" class="fp-empty-filters">
            الفلاتر النشطة:
            <span class="fp-chip" v-for="(c, i) in activeFilterChips" :key="i">{{ c }}</span>
          </div>
          <button v-if="anyFilterActive" class="btn btn-blue" @click="resetFilters">مسح الفلاتر</button>
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
              <div><div class="vc-plate">{{ v.plate }}</div></div>
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
              <span v-if="v.vehicle_status === 'workshop' && v.workshop_date" style="font-size:10px;color:var(--orange-l);font-family:'JetBrains Mono',monospace;display:inline-flex;align-items:center;gap:3px"><Icon name="calendar" :size="11" /> {{ v.workshop_date }}</span>
              <span v-else-if="v.vehicle_status !== 'assigned' && v.vehicle_status !== 'workshop'" style="font-size:10px;color:var(--t3)">{{ v.history.length }} سائق سابق</span>
            </div>
            <!-- Fuel row (renders the "—" empty path; live API has no fuel rate) -->
            <div class="vc-fuel-row" @click.stop>
              <div>
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
                  <span class="fuel-grade-badge">{{ fuelView(v).gradeLabel }} · {{ fuelView(v).sarPerL }} ر.س/ل</span>
                </div>
                <div style="display:flex;align-items:baseline;gap:4px">
                  <span class="fuel-sar-val">{{ fuelView(v).sarDisplay }}</span>
                  <span class="fuel-sar-unit">ر.س</span>
                  <span class="fuel-sar-period">/يوم</span>
                  <span v-if="fuelView(v).dailySAR > 0" class="fuel-monthly" style="margin-right:8px">· {{ fuelView(v).monDisplay }} ر.س/شهر</span>
                </div>
              </div>
            </div>
            <div v-if="v.vehicle_status === 'workshop'" class="vc-workshop-stripe"><Icon name="wrench" :size="13" /> {{ v.workshop_notes || "في الصيانة" }}</div>
            <div v-if="v.vehicle_status === 'stolen'" class="vc-stolen-stripe"><Icon name="shield-alert" :size="13" /> مسروق <template v-if="v.stolen_info && v.stolen_info.date">· {{ v.stolen_info.date }}</template></div>
            <div v-if="(v.damages || []).length || (v.accidents || []).length" style="padding:3px 14px;display:flex;gap:6px;border-top:1px solid var(--b1)">
              <span v-if="(v.damages || []).length" style="font-size:10px;padding:2px 7px;background:var(--red-d);color:var(--red-l);border-radius:6px;border:1px solid rgba(220,38,38,.2);display:inline-flex;align-items:center;gap:3px"><Icon name="hammer" :size="11" /> {{ v.damages.length }} تلف</span>
              <span v-if="(v.accidents || []).length" style="font-size:10px;padding:2px 7px;background:var(--amber-d);color:var(--amber-l);border-radius:6px;border:1px solid rgba(217,119,6,.2);display:inline-flex;align-items:center;gap:3px"><Icon name="crash" :size="11" /> {{ v.accidents.length }} حادثة</span>
            </div>
            <div v-if="v.current_driver" class="vc-driver">
              <div class="drv-av">{{ initials(v.current_driver) }}</div>
              <div class="drv-info">
                <div class="drv-name">{{ v.current_driver.name_ar || v.current_driver.name_en || "—" }}</div>
                <div class="drv-since">منذ {{ v.current_driver.date_receive || "—" }} · {{ trim(v.current_driver.project) || "—" }}</div>
              </div>
              <span class="lock-ico"><Icon name="lock" :size="15" /></span>
            </div>
            <div v-else class="no-driver">
              <template v-if="v.vehicle_status === 'available'"><Icon name="key" :size="14" /> جاهزة للتخصيص</template>
              <template v-else-if="v.vehicle_status === 'workshop'"><Icon name="wrench" :size="14" /> في الصيانة</template>
              <template v-else><Icon name="circle-pause" :size="14" /> خارج الخدمة</template>
            </div>
            <div v-if="calcTotalDaysNum(v) > 0" class="vc-dur">
              <div class="dur-label">
                <span>إجمالي التشغيل: {{ calcTotalDaysNum(v) }} يوم</span>
                <span>{{ v.history.length ? v.history[0].date_receive || "" : "" }}</span>
              </div>
              <div class="dur-bar"><div class="dur-fill" :style="{ width: Math.min(100, Math.round((calcTotalDaysNum(v) / 400) * 100)) + '%' }"></div></div>
            </div>
            <div class="vc-actions" @click.stop>
              <template v-if="v.vehicle_status === 'assigned'">
                <button class="ac ac-stop" title="إيقاف السائق وقفل الملف" @click="quickStop(v.plate)"><span class="ac-ico"><Icon name="circle-pause" :size="14" /></span>إيقاف</button>
                <button class="ac ac-reassign" title="تفويض لسائق جديد" @click="quickReassign(v.plate)"><span class="ac-ico"><Icon name="rotate-cw" :size="14" /></span>تفويض</button>
                <button class="ac ac-workshop" title="إرسال للورشة بعد الإيقاف" @click="quickStop(v.plate, true)"><span class="ac-ico"><Icon name="wrench" :size="14" /></span>ورشة</button>
              </template>
              <template v-else-if="v.vehicle_status === 'available'">
                <button class="ac ac-free" title="تخصيص سائق جديد" @click="quickReassign(v.plate)"><span class="ac-ico"><Icon name="key" :size="14" /></span>تخصيص</button>
                <button class="ac ac-workshop" title="إرسال للورشة" @click="sendWorkshop(v.plate)"><span class="ac-ico"><Icon name="wrench" :size="14" /></span>ورشة</button>
              </template>
              <template v-else-if="v.vehicle_status === 'workshop'">
                <button class="ac ac-free" title="خروج من الورشة" @click="exitWorkshop(v.plate)"><span class="ac-ico"><Icon name="circle-check" :size="14" /></span>خروج</button>
                <button class="ac ac-reassign" title="تخصيص سائق مباشرة" @click="quickReassign(v.plate)"><span class="ac-ico"><Icon name="key" :size="14" /></span>تخصيص</button>
              </template>
              <template v-else>
                <button class="ac ac-free" title="تعيين كمتاح" @click="setAvailable(v.plate)"><span class="ac-ico"><Icon name="circle-dot" :size="14" /></span>متاح</button>
                <button class="ac ac-workshop" title="إرسال للورشة" @click="sendWorkshop(v.plate)"><span class="ac-ico"><Icon name="wrench" :size="14" /></span>ورشة</button>
              </template>
              <button v-if="v.vehicle_status === 'stolen'" class="ac" style="border-color:rgba(124,58,237,.25);color:var(--purple-l)" @click="recoverVehicle(v.plate)"><span class="ac-ico"><Icon name="lock-open" :size="14" /></span>استرداد</button>
              <button v-else-if="v.vehicle_status === 'available'" class="ac" style="border-color:rgba(220,38,38,.25);color:var(--red-l)" @click="markStolen(v.plate)"><span class="ac-ico"><Icon name="shield-alert" :size="14" /></span>مسروق</button>
              <button class="ac ac-hist" title="عرض السجل الكامل" @click="openPanel(v.plate, 5)"><span class="ac-ico"><Icon name="clipboard-list" :size="14" /></span><span class="hist-n">{{ v.history.length }}</span></button>
            </div>
          </div>
        </div>
      </div>

      <!-- TABLE -->
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th @click="onSortCol('sheet')">النوع</th>
              <th @click="onSortCol('plate')">اللوحة</th>
              <th @click="onSortCol('vehicle_type')">المركبة</th>
              <th @click="onSortCol('rental_office')">المكتب</th>
              <th @click="onSortCol('vehicle_status')">حالة المركبة</th>
              <th>السائق الحالي</th>
              <th @click="onSortCol('project')">المشروع</th>
              <th @click="onSortCol('area')">المنطقة</th>
              <th>عدد السائقين</th>
              <th>مدة التشغيل</th>
              <th>إجراء</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filtered.length"><td colspan="11"><div class="empty"><div class="empty-ic"><Icon name="search" :size="42" :stroke-width="1.5" /></div>لا نتائج</div></td></tr>
            <tr v-for="v in filtered" :key="v.plate" @click="openPanel(v.plate)">
              <td><Icon :name="icon(v)" :size="18" /></td>
              <td><span class="mono" style="font-weight:700;color:var(--t1)">{{ v.plate }}</span></td>
              <td>{{ v.vehicle_type }}</td>
              <td>{{ v.rental_office }}</td>
              <td><span class="sbadge" :class="sb(v).cls" style="display:inline-flex;gap:4px"><Icon :name="sb(v).ic" :size="12" />{{ SL[v.vehicle_status] || v.vehicle_status }}</span></td>
              <td><template v-if="v.current_driver">{{ v.current_driver.name_ar || v.current_driver.name_en }} <Icon name="lock" :size="13" /></template><span v-else style="color:var(--t3)">—</span></td>
              <td>{{ trim(v.project) || "—" }}</td>
              <td>{{ v.area }}</td>
              <td style="color:var(--purple-l)">{{ v.history.length }}</td>
              <td style="color:var(--amber-l);font-family:'JetBrains Mono',monospace">{{ calcTotalDaysNum(v) ? calcTotalDaysNum(v) + " يوم" : "—" }}</td>
              <td @click.stop>
                <button class="btn" style="padding:3px 10px;font-size:11px" @click="openPanel(v.plate)">تفاصيل <Icon name="chevron" :size="13" /></button>
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
          <div class="ph-plate">{{ panel.vehicle.plate }}</div>
          <div class="ph-sub">{{ panel.vehicle.vehicle_type }} · {{ panel.vehicle.rental_office }} · <Icon :name="panel.vehicle.sheet === 'CAR' ? 'car' : 'bike'" :size="13" /> {{ panel.vehicle.sheet === "CAR" ? "سيارة" : "دباب" }}</div>
          <div class="ph-tags">
            <span class="tag">{{ trim(panel.vehicle.fuel) || "—" }}</span>
            <span class="tag">{{ trim(panel.vehicle.project) || "بدون مشروع" }}</span>
            <span class="tag"><Icon name="pin" :size="11" /> {{ panel.vehicle.area }}</span>
            <span class="sbadge" :class="sb(panel.vehicle).cls" style="font-size:10px;display:inline-flex;gap:4px"><Icon :name="sb(panel.vehicle).ic" :size="11" />{{ sb(panel.vehicle).label }}</span>
          </div>
        </div>
        <button class="panel-close" @click="closePanel"><Icon name="x" :size="18" /></button>
      </div>
      <div class="panel-tabs" style="flex-wrap:wrap">
        <button class="ptab" :class="{ on: panel.tab === 0 }" @click="setPTab(0)"><Icon name="home" :size="14" /> نظرة عامة</button>
        <button class="ptab" :class="{ on: panel.tab === 1 }" @click="setPTab(1)"><Icon name="user" :size="14" /> السائق</button>
        <button class="ptab" :class="{ on: panel.tab === 2 }" @click="setPTab(2)"><Icon name="settings" :size="14" /> الحالة</button>
        <button class="ptab" :class="{ on: panel.tab === 3 }" @click="setPTab(3)"><Icon name="hammer" :size="14" /> التلفيات<span v-if="tabDmg" class="ptab-badge">{{ tabDmg }}</span></button>
        <button class="ptab" :class="{ on: panel.tab === 4 }" @click="setPTab(4)"><Icon name="crash" :size="14" /> الحوادث<span v-if="tabAcc" class="ptab-badge" style="background:var(--amber-l)">{{ tabAcc }}</span></button>
        <button class="ptab" :class="{ on: panel.tab === 5 }" @click="setPTab(5)"><Icon name="clipboard-list" :size="14" /> السجل</button>
      </div>
      <div class="panel-body">
        <!-- TAB 0: OVERVIEW -->
        <div v-if="panel.tab === 0" class="pb on">
          <div class="psect-title"><Icon name="chart-column" :size="14" /> إحصائيات المركبة</div>
          <div class="pstats">
            <div class="pstat"><div class="pstat-n" style="color:var(--purple-l)">{{ panel.vehicle.history.length }}</div><div class="pstat-l">إجمالي السائقين</div></div>
            <div class="pstat"><div class="pstat-n" style="color:var(--amber-l)">{{ calcTotalDaysNum(panel.vehicle) }}</div><div class="pstat-l">أيام التشغيل</div></div>
            <div class="pstat"><div class="pstat-n" style="color:var(--green-l)">{{ calcActiveDaysNum(panel.vehicle) }}</div><div class="pstat-l">أيام نشطة</div></div>
            <div class="pstat"><div class="pstat-n" style="color:var(--cyan-l)">{{ panel.vehicle.history.filter((h) => h.status === "Active").length }}</div><div class="pstat-l">مرات التفعيل</div></div>
          </div>
          <div class="psect-title"><Icon name="search" :size="14" /> تفاصيل المركبة</div>
          <div class="kv-grid">
            <div class="kv"><div class="kv-l">اللوحة</div><div class="kv-v mono" style="font-size:16px;letter-spacing:2px">{{ panel.vehicle.plate }}</div></div>
            <div class="kv"><div class="kv-l">النوع</div><div class="kv-v"><Icon :name="panel.vehicle.sheet === 'CAR' ? 'car' : 'bike'" :size="14" /> {{ panel.vehicle.sheet === "CAR" ? "سيارة" : "دباب" }}</div></div>
            <div class="kv"><div class="kv-l">الطراز</div><div class="kv-v">{{ panel.vehicle.vehicle_type || "—" }}</div></div>
            <div class="kv"><div class="kv-l">الوقود</div><div class="kv-v">{{ panel.vehicle.fuel || "—" }}</div></div>
            <div class="kv"><div class="kv-l">مكتب الإيجار</div><div class="kv-v">{{ panel.vehicle.rental_office || "—" }}</div></div>
            <div class="kv"><div class="kv-l">المنطقة</div><div class="kv-v">{{ panel.vehicle.area || "—" }}</div></div>
            <div class="kv"><div class="kv-l">المشروع</div><div class="kv-v">{{ trim(panel.vehicle.project) || "—" }}</div></div>
            <div class="kv"><div class="kv-l">حالة المركبة</div><div class="kv-v">{{ sb(panel.vehicle).label }}</div></div>
          </div>
          <template v-if="panel.vehicle.current_driver">
            <div class="psect-title"><Icon name="user" :size="14" /> السائق الحالي</div>
            <div class="cur-driver-card">
              <div class="cdc-av">{{ initials(panel.vehicle.current_driver) }}</div>
              <div class="cdc-info">
                <div class="cdc-name">{{ panel.vehicle.current_driver.name_ar || panel.vehicle.current_driver.name_en || "—" }}</div>
                <div class="cdc-en">{{ panel.vehicle.current_driver.name_en || "" }}</div>
                <div class="cdc-chips">
                  <span class="cdc-chip"><Icon name="phone" :size="11" /> {{ panel.vehicle.current_driver.mobile || "—" }}</span>
                  <span class="cdc-chip"><Icon name="id-card" :size="11" /> {{ panel.vehicle.current_driver.driver_id || "—" }}</span>
                  <span class="cdc-chip"><Icon name="calendar" :size="11" /> {{ panel.vehicle.current_driver.date_receive || "—" }}</span>
                </div>
              </div>
              <span class="lock-pill"><Icon name="lock" :size="12" /> نشط</span>
            </div>
          </template>
        </div>

        <!-- TAB 1: DRIVER -->
        <div v-else-if="panel.tab === 1" class="pb on">
          <template v-if="panel.vehicle.current_driver">
            <div class="alert alert-green"><Icon name="lock" :size="15" /> الملف مقفل — المركبة مُسندة للسائق {{ panel.vehicle.current_driver.name_ar || panel.vehicle.current_driver.name_en }}</div>
            <div class="psect-title">بيانات السائق الحالي</div>
            <div class="kv-grid">
              <div class="kv"><div class="kv-l">الاسم عربي</div><div class="kv-v">{{ panel.vehicle.current_driver.name_ar || "—" }}</div></div>
              <div class="kv"><div class="kv-l">الاسم إنجليزي</div><div class="kv-v">{{ panel.vehicle.current_driver.name_en || "—" }}</div></div>
              <div class="kv"><div class="kv-l">رقم الإقامة</div><div class="kv-v mono">{{ panel.vehicle.current_driver.driver_id || "—" }}</div></div>
              <div class="kv"><div class="kv-l">الجوال</div><div class="kv-v mono">{{ panel.vehicle.current_driver.mobile || "—" }}</div></div>
              <div class="kv"><div class="kv-l">المشروع</div><div class="kv-v">{{ trim(panel.vehicle.current_driver.project) || "—" }}</div></div>
              <div class="kv"><div class="kv-l">المنطقة</div><div class="kv-v">{{ panel.vehicle.current_driver.area || "—" }}</div></div>
              <div class="kv"><div class="kv-l">تاريخ الاستلام</div><div class="kv-v mono">{{ panel.vehicle.current_driver.date_receive || "—" }}</div></div>
              <div class="kv"><div class="kv-l">فرع الاستلام</div><div class="kv-v">{{ panel.vehicle.current_driver.branch_receive || "—" }}</div></div>
            </div>
            <div class="psect-title">الإجراءات</div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-red" style="flex:1" @click="openStopForm"><Icon name="circle-pause" :size="15" /> إيقاف وقفل الملف</button>
              <button class="btn btn-green" style="flex:1" @click="openReassignForm"><Icon name="rotate-cw" :size="15" /> تفويض لسائق جديد</button>
            </div>
            <!-- Stop sub-form -->
            <div v-if="subForm === 'stop'" style="margin-top:14px;border:1px solid rgba(244,63,94,.2);border-radius:var(--r2);padding:14px;background:var(--red-d)">
              <div class="psect-title" style="color:var(--red-l)"><Icon name="circle-pause" :size="14" /> إيقاف السائق وقفل الملف</div>
              <div class="form-grid" style="margin-bottom:10px">
                <div class="ff"><div class="fl">تاريخ التسليم *</div><input class="fi" type="date" v-model="sf.date" /></div>
                <div class="ff"><div class="fl">فرع التسليم</div><input class="fi" v-model="sf.branch" placeholder="الفرع" /></div>
                <div class="ff"><div class="fl">سبب الإيقاف</div>
                  <select class="fsel" v-model="sf.reason">
                    <option value="">— اختر السبب —</option>
                    <option>انتهاء العقد</option><option>نقل لمشروع آخر</option>
                    <option>إيقاف المشروع</option><option>عطل المركبة</option>
                    <option>طلب السائق</option><option>مخالفة</option><option>أخرى</option>
                  </select>
                </div>
                <div class="ff"><div class="fl">الحالة بعد الإيقاف</div>
                  <select class="fsel" v-model="sf.nextStatus">
                    <option value="available">متاح في المكتب</option>
                    <option value="workshop">إرسال للورشة</option>
                    <option value="stopped">متوقف</option>
                  </select>
                </div>
              </div>
              <div class="ff"><div class="fl">ملاحظات</div><textarea class="fta" v-model="sf.notes" placeholder="أي ملاحظات..."></textarea></div>
              <div class="form-actions" style="margin-top:10px">
                <button class="btn" @click="subForm = null">إلغاء</button>
                <button class="btn btn-red" @click="confirmStop"><Icon name="circle-pause" :size="15" /> تأكيد الإيقاف وقفل الملف</button>
              </div>
            </div>
            <!-- Reassign sub-form -->
            <div v-if="subForm === 'reassign'" style="margin-top:14px;border:1px solid rgba(0,201,122,.2);border-radius:var(--r2);padding:14px;background:var(--green-d)">
              <div class="psect-title" style="color:var(--green-l)"><Icon name="rotate-cw" :size="14" /> تفويض لسائق جديد</div>
              <div class="alert alert-amber" style="margin-bottom:12px"><Icon name="triangle-alert" :size="15" /> سيتم قفل ملف السائق الحالي ({{ panel.vehicle.current_driver.name_ar || panel.vehicle.current_driver.name_en || "—" }}) تلقائياً قبل فتح الملف الجديد</div>
              <div class="psect-title" style="color:var(--green-l);margin-top:12px">بيانات السائق الجديد</div>
              <div class="form-grid">
                <div class="ff"><div class="fl">الاسم بالعربي *</div><input class="fi" v-model="rf.nameAr" placeholder="اسم السائق" /></div>
                <div class="ff"><div class="fl">الاسم بالإنجليزي</div><input class="fi" v-model="rf.nameEn" placeholder="Driver Name" /></div>
                <div class="ff"><div class="fl">رقم الإقامة *</div><input class="fi mono" v-model="rf.iqama" placeholder="2XXXXXXXXX" /></div>
                <div class="ff"><div class="fl">رقم الجوال *</div><input class="fi" v-model="rf.mobile" placeholder="05XXXXXXXX" /></div>
                <div class="ff"><div class="fl">المشروع</div>
                  <select class="fsel" v-model="rf.project"><option>KEETA</option><option>SHIPMENT</option><option>KEEMART</option><option>NINJA</option><option>NOON</option><option>ARAMEX</option></select>
                </div>
                <div class="ff"><div class="fl">المنطقة</div>
                  <select class="fsel" v-model="rf.area"><option>RIYADH</option><option>JADAH</option><option>MAKA</option><option>DAMAM</option><option>TAIF</option></select>
                </div>
                <div class="ff"><div class="fl">تاريخ الاستلام</div><input class="fi" type="date" v-model="rf.date" /></div>
                <div class="ff"><div class="fl">فرع الاستلام</div><input class="fi" v-model="rf.branch" placeholder="الفرع" /></div>
              </div>
              <div class="form-actions" style="margin-top:12px">
                <button class="btn" @click="subForm = null">إلغاء</button>
                <button class="btn btn-green" @click="submitReassign"><Icon name="lock" :size="15" /> تخصيص وقفل الملف</button>
              </div>
            </div>
          </template>
          <template v-else>
            <div v-if="panel.vehicle.vehicle_status === 'workshop'" class="alert alert-orange"><Icon name="wrench" :size="15" /> المركبة في الورشة — أخرجها أولاً لتخصيص سائق</div>
            <div v-if="panel.vehicle.vehicle_status === 'stopped'" class="alert alert-amber"><Icon name="circle-pause" :size="15" /> المركبة متوقفة — غيّر حالتها لـ"متاح" لتخصيص سائق</div>
            <div class="psect-title">تخصيص سائق جديد</div>
            <div class="form-grid">
              <div class="ff"><div class="fl">الاسم بالعربي *</div><input class="fi" v-model="rf.nameAr" placeholder="اسم السائق" /></div>
              <div class="ff"><div class="fl">الاسم بالإنجليزي</div><input class="fi" v-model="rf.nameEn" placeholder="Driver Name" /></div>
              <div class="ff"><div class="fl">رقم الإقامة *</div><input class="fi mono" v-model="rf.iqama" placeholder="2XXXXXXXXX" /></div>
              <div class="ff"><div class="fl">رقم الجوال *</div><input class="fi" v-model="rf.mobile" placeholder="05XXXXXXXX" /></div>
              <div class="ff"><div class="fl">المشروع</div>
                <select class="fsel" v-model="rf.project"><option>KEETA</option><option>SHIPMENT</option><option>KEEMART</option><option>NINJA</option><option>NOON</option><option>ARAMEX</option></select>
              </div>
              <div class="ff"><div class="fl">المنطقة</div>
                <select class="fsel" v-model="rf.area"><option>RIYADH</option><option>JADAH</option><option>MAKA</option><option>DAMAM</option><option>TAIF</option></select>
              </div>
              <div class="ff"><div class="fl">تاريخ الاستلام</div><input class="fi" type="date" v-model="rf.date" /></div>
              <div class="ff"><div class="fl">فرع الاستلام</div><input class="fi" v-model="rf.branch" placeholder="الفرع" /></div>
            </div>
            <div class="form-actions" style="margin-top:12px">
              <button class="btn btn-green" @click="submitReassign"><Icon name="lock" :size="15" /> تخصيص وقفل الملف</button>
            </div>
          </template>
        </div>

        <!-- TAB 2: STATUS -->
        <div v-else-if="panel.tab === 2" class="pb on">
          <div class="psect-title">تغيير حالة المركبة</div>
          <div class="status-grid">
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'assigned' ? 'cur-assigned' : ''" @click="changeStatus(panel.vehicle.plate, 'assigned')">
              <span class="sp-ico"><Icon name="lock" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'assigned' ? 'inherit' : 'var(--t2)' }">مُسند لسائق</span><span class="sp-desc">مرتبط بسائق نشط — الملف مقفل</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'available' ? 'cur-available' : ''" @click="changeStatus(panel.vehicle.plate, 'available')">
              <span class="sp-ico"><Icon name="key" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'available' ? 'inherit' : 'var(--t2)' }">متاح في المكتب</span><span class="sp-desc">جاهز للتخصيص لأي سائق</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'workshop' ? 'cur-workshop' : ''" @click="changeStatus(panel.vehicle.plate, 'workshop')">
              <span class="sp-ico"><Icon name="wrench" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'workshop' ? 'inherit' : 'var(--t2)' }">في الورشة</span><span class="sp-desc">تحت الصيانة — غير متاح</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'stopped' ? 'cur-stopped' : ''" @click="changeStatus(panel.vehicle.plate, 'stopped')">
              <span class="sp-ico"><Icon name="circle-pause" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'stopped' ? 'inherit' : 'var(--t2)' }">متوقف</span><span class="sp-desc">خارج الخدمة مؤقتاً</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'stolen' ? 'cur-stopped' : ''" @click="changeStatus(panel.vehicle.plate, 'stolen')">
              <span class="sp-ico"><Icon name="shield-alert" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'stolen' ? 'inherit' : 'var(--t2)' }">مسروقة</span><span class="sp-desc">تم الإبلاغ عن السرقة</span>
            </button>
          </div>
          <template v-if="panel.vehicle.vehicle_status === 'workshop'">
            <button class="btn btn-green" style="width:100%;justify-content:center" @click="changeStatus(panel.vehicle.plate, 'available')"><Icon name="circle-check" :size="15" /> خروج من الورشة — تعيين كمتاح</button>
          </template>
          <template v-if="panel.vehicle.vehicle_status === 'stolen'">
            <button class="btn btn-green" style="width:100%;justify-content:center;margin-top:8px" @click="recoverVehicle(panel.vehicle.plate)"><Icon name="lock-open" :size="15" /> استرداد المركبة — تعيين كمتاح</button>
          </template>
          <template v-if="panel.vehicle.vehicle_status === 'available' || panel.vehicle.vehicle_status === 'stopped'">
            <div class="psect-title" style="color:var(--red-l)"><Icon name="shield-alert" :size="14" /> تسجيل سرقة</div>
            <button class="btn btn-red" style="width:100%;justify-content:center" @click="openStolenForm"><Icon name="shield-alert" :size="15" /> تسجيل بلاغ سرقة</button>
            <div v-if="subForm === 'stolen'" style="border:1px solid rgba(124,58,237,.2);border-radius:var(--r2);padding:14px;background:var(--purple-d);margin-top:10px">
              <div class="psect-title" style="color:var(--purple-l)"><Icon name="shield-alert" :size="14" /> تفاصيل بلاغ السرقة</div>
              <div class="form-grid">
                <div class="ff"><div class="fl">تاريخ السرقة *</div><input class="fi" type="date" v-model="stf.date" /></div>
                <div class="ff"><div class="fl">رقم بلاغ الشرطة</div><input class="fi mono" v-model="stf.police" placeholder="رقم المرجع" /></div>
                <div class="ff"><div class="fl">موقع السرقة</div><input class="fi" v-model="stf.location" placeholder="المدينة / الموقع" /></div>
                <div class="ff"><div class="fl">تم الإبلاغ بواسطة</div><input class="fi" v-model="stf.reporter" placeholder="الاسم" /></div>
                <div class="ff" style="grid-column:1/-1"><div class="fl">تفاصيل الحادثة</div><textarea class="fta" v-model="stf.desc" placeholder="اكتب تفاصيل السرقة..."></textarea></div>
                <div class="ff" style="grid-column:1/-1"><div class="fl">ملاحظات إضافية</div><textarea class="fta" v-model="stf.notes"></textarea></div>
              </div>
              <div class="form-actions" style="margin-top:10px">
                <button class="btn" @click="subForm = null">إلغاء</button>
                <button class="btn" style="background:var(--purple);color:#fff;border-color:var(--purple)" @click="submitStolen"><Icon name="shield-alert" :size="15" /> تأكيد تسجيل السرقة</button>
              </div>
            </div>
          </template>
        </div>

        <!-- TAB 3: DAMAGES (live API has none → empty state) -->
        <div v-else-if="panel.tab === 3" class="pb on">
          <div class="psect-title"><Icon name="hammer" :size="14" /> سجل التلفيات</div>
          <div v-if="!(panel.vehicle.damages || []).length" class="empty"><div class="empty-ic"><Icon name="hammer" :size="42" :stroke-width="1.5" /></div><div>لا توجد تلفيات مسجلة</div></div>
          <div v-for="(d, i) in panel.vehicle.damages || []" :key="i" class="incident-card">
            <div class="incident-card-head">
              <div style="display:flex;align-items:center;gap:8px">
                <span class="incident-badge" :class="d.status === 'completed' ? 'incident-badge-ok' : ''"><Icon :name="d.status === 'completed' ? 'circle-check' : 'hammer'" :size="12" />{{ d.status === "completed" ? "مُصلح" : "تلف" }}</span>
                <span style="font-size:12px;font-weight:600;color:var(--t1)">{{ d.date || "—" }}</span>
              </div>
              <div style="display:flex;gap:6px"><span v-if="d.cost" style="font-size:11px;color:var(--amber-l);font-weight:600;display:inline-flex;align-items:center;gap:3px"><Icon name="banknote" :size="12" /> {{ d.cost }} ر.س</span></div>
            </div>
            <div class="incident-card-body">
              <div class="inc-row"><span class="inc-label">الوصف</span>{{ d.description || "—" }}</div>
            </div>
          </div>
        </div>

        <!-- TAB 4: ACCIDENTS (live API has none → empty state) -->
        <div v-else-if="panel.tab === 4" class="pb on">
          <div class="psect-title"><Icon name="crash" :size="14" /> سجل الحوادث</div>
          <div v-if="!(panel.vehicle.accidents || []).length" class="empty"><div class="empty-ic"><Icon name="crash" :size="42" :stroke-width="1.5" /></div><div>لا توجد حوادث مسجلة</div></div>
          <div v-for="(a, i) in panel.vehicle.accidents || []" :key="i" class="incident-card">
            <div class="incident-card-head">
              <div style="display:flex;align-items:center;gap:8px">
                <span class="incident-badge incident-badge-acc" :class="a.status === 'closed' ? 'incident-badge-ok' : ''"><Icon :name="a.status === 'closed' ? 'circle-check' : 'crash'" :size="12" />{{ a.status === "closed" ? "مغلق" : "حادثة" }}</span>
                <span style="font-size:12px;font-weight:600;color:var(--t1)">{{ a.date || "—" }}</span>
              </div>
            </div>
            <div class="incident-card-body">
              <div class="inc-row"><span class="inc-label">الوصف</span>{{ a.description || "—" }}</div>
            </div>
          </div>
        </div>

        <!-- TAB 5: LOG -->
        <div v-else-if="panel.tab === 5" class="pb on">
          <div v-if="!panel.vehicle.history.length" class="empty"><div class="empty-ic"><Icon name="clipboard-list" :size="42" :stroke-width="1.5" /></div><div>لا توجد سجلات</div></div>
          <template v-else>
            <div class="psect-title">السجل الزمني الكامل ({{ panel.vehicle.history.length }} سائق)</div>
            <div class="tl">
              <div v-for="(item, i) in historyItems(panel.vehicle)" :key="i" class="tl-item">
                <div class="tl-ic" :class="item.d.status === 'Active' ? 'ti-active' : 'ti-stopped'"><Icon name="user" :size="15" /></div>
                <div class="tl-info">
                  <div class="tl-head">
                    {{ item.d.name_ar || item.d.name_en || "سائق" }}
                    <span class="tl-status" :class="item.d.status === 'Active' ? 'tls-active' : 'tls-stopped'"><Icon :name="item.d.status === 'Active' ? 'circle-check' : 'circle-pause'" :size="11" />{{ item.d.status === "Active" ? "نشط" : "انتهى" }}</span>
                  </div>
                  <div class="tl-sub">{{ item.d.name_en || "" }} · <Icon name="phone" :size="11" /> {{ item.d.mobile || "—" }} · <Icon name="id-card" :size="11" /> {{ item.d.driver_id || "—" }}</div>
                  <div class="tl-sub"><Icon name="package" :size="11" /> {{ trim(item.d.project) || "—" }} · <Icon name="pin" :size="11" /> {{ item.d.area || "—" }} · <Icon name="building" :size="11" /> {{ item.d.branch_receive || "—" }}</div>
                  <span class="tl-dates">{{ item.d.date_receive || "—" }} → {{ item.d.date_deliver || (item.d.status === "Active" ? "جارٍ" : "—") }}</span>
                  <span v-if="calcDur(item.d.date_receive, item.d.date_deliver || (item.d.status === 'Active' ? today() : ''))" class="tl-dur">{{ calcDur(item.d.date_receive, item.d.date_deliver || (item.d.status === "Active" ? today() : "")) }}</span>
                  <div v-if="item.d.reason" class="tl-reason">سبب: {{ item.d.reason }}</div>
                  <div v-if="item.d.notes" class="tl-note">ملاحظة: {{ item.d.notes }}</div>
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
        <button class="btn" @click="cfDo(false)">إلغاء</button>
        <button class="btn" :class="cf.okCls" @click="cfDo(true)">{{ cf.okLabel }}</button>
      </div>
    </div>
  </div>
</template>
