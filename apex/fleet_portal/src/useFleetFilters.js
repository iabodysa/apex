// Copyright (c) 2026, AFMCO and contributors
// All board filtering/sorting/view state: the filter model, the filtered+sorted
// list (his applyFilters), the driver-centric grouping, the empty-state chips,
// board density, and the mobile filter-sheet toggle.
import { reactive, ref, computed } from "vue";

export function useFleetFilters({ vehicles, fmt, t }) {
  const { expiryFlag, trim, statusKey, calcTotalDaysNum } = fmt;

  // Filter model (mirrors his applyFilters inputs).
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
  // The two triage pills are opt-in client filters layered on the base list.
  const triageFilter = ref(""); // "" | incidents | expiring

  const setSP = (s) => (f.status = s);
  const setSheet = (v) => (f.sheet = v);
  const setFuel = (v) => (f.fuel = v);
  const setDateType = (v) => (f.dateType = v);
  const setView = (v) => (f.view = v);
  function setTriage(kind) {
    triageFilter.value = triageFilter.value === kind ? "" : kind;
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
    triageFilter.value = "";
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
        f.dateTo ||
        triageFilter.value
      )
  );

  // The filtered + sorted list — a faithful port of his applyFilters body.
  const filtered = computed(() => {
    const q = f.search.toLowerCase();
    let list = vehicles.value.filter((v) => {
      if (triageFilter.value === "incidents") {
        const open =
          (v.damages || []).some((d) => d.status !== "completed") ||
          (v.accidents || []).some((a) => a.status !== "closed");
        if (!open) return false;
      }
      if (triageFilter.value === "expiring" && !expiryFlag(v).show) return false;
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

  // Driver-centric grouping — a read-only reorganization of the SAME filtered
  // vehicles into per-driver groups (adds no data the board doesn't already hold).
  const driverGroups = computed(() => {
    const byDriver = new Map();
    const unassigned = [];
    for (const v of filtered.value) {
      const d = v.current_driver;
      if (!d) {
        unassigned.push(v);
        continue;
      }
      const key = d.driver_id || d.name_en || d.name_ar || v.plate;
      if (!byDriver.has(key)) {
        byDriver.set(key, { key, driver: d, vehicles: [] });
      }
      byDriver.get(key).vehicles.push(v);
    }
    const groups = Array.from(byDriver.values()).sort((a, b) =>
      (a.driver.name_ar || a.driver.name_en || "").localeCompare(
        b.driver.name_ar || b.driver.name_en || "",
        "ar"
      )
    );
    if (unassigned.length) {
      groups.push({ key: "__unassigned__", driver: null, vehicles: unassigned });
    }
    return groups;
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

  // Board density (compact tightens card rows), persisted per user.
  const DENSITY_KEY = "fleet_portal_density";
  function initDensity() {
    try {
      const saved = localStorage.getItem(DENSITY_KEY);
      if (saved === "compact" || saved === "comfortable") return saved;
    } catch (e) {
      /* storage blocked */
    }
    return "comfortable";
  }
  const density = ref(initDensity());
  function toggleDensity() {
    density.value = density.value === "compact" ? "comfortable" : "compact";
    try {
      localStorage.setItem(DENSITY_KEY, density.value);
    } catch (e) {
      /* storage blocked */
    }
  }

  // Mobile filter sheet (the sidebar becomes a bottom sheet on phones).
  const filtersSheetOpen = ref(false);
  function toggleFiltersSheet() {
    filtersSheetOpen.value = !filtersSheetOpen.value;
  }
  function closeFiltersSheet() {
    filtersSheetOpen.value = false;
  }

  return {
    f, sortCol, sortDir, triageFilter,
    setSP, setSheet, setFuel, setDateType, setView, setTriage, onSortCol,
    setQuickDate, clearDateFilter, resetFilters,
    hasDateFilter, anyFilterActive, filtered, driverGroups, dateInfo, activeFilterChips,
    density, toggleDensity,
    filtersSheetOpen, toggleFiltersSheet, closeFiltersSheet,
  };
}
