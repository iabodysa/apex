// Copyright (c) 2026, afmcoltd
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

/* Every piece of board state a person expects to survive lives in the address, and only there.
 *
 * The board used to hold filters, search, the status pill, the triage toggle, the sort, the
 * view, the open vehicle and the alerts drawer in memory, so a refresh, a Back press or a link
 * sent to a colleague lost every one of them. There is no second store below: each getter
 * reads the query and each setter writes it, which is also why "clear filters" can no longer
 * miss the key the list actually sorts by — there is exactly one sort key to clear.
 *
 * Density stays in localStorage on purpose: it is a preference of this screen on this device,
 * not something a shared link should impose on the reader. */

export const VIEWS = ["cards", "table", "drivers"];
export const PANEL_TABS = ["overview", "driver", "status", "damages", "accidents", "log"];
export const SORT_KEYS = [
  "plate",
  "status",
  "vehicle_type",
  "sheet",
  "rental_office",
  "project",
  "area",
  "drivers_desc",
  "duration_desc",
];

const DEFAULTS = {
  q: "",
  status: "",
  triage: "",
  type: "",
  fuel: "",
  project: "",
  area: "",
  office: "",
  dateType: "receive",
  from: "",
  to: "",
  sort: "plate",
  dir: "asc",
  view: "table",
  vehicle: "",
  vtab: "overview",
  alerts: "",
};

/* Filters only. `view`, the open vehicle, the panel tab and the drawer are places the reader
   navigated to, not narrowings he applied, so clearing the filters leaves them alone. */
const FILTER_KEYS = [
  "q",
  "status",
  "triage",
  "type",
  "fuel",
  "project",
  "area",
  "office",
  "dateType",
  "from",
  "to",
  "sort",
  "dir",
];

export function useBoardState() {
  const route = useRoute();
  const router = useRouter();

  const read = (key) => {
    const raw = route.query[key];
    const value = Array.isArray(raw) ? raw[0] : raw;
    return value == null || value === "" ? DEFAULTS[key] : String(value);
  };

  function write(patch, { push = false } = {}) {
    const query = { ...route.query };
    for (const [key, value] of Object.entries(patch)) {
      if (value == null || value === "" || value === DEFAULTS[key]) delete query[key];
      else query[key] = String(value);
    }
    const go = push ? router.push : router.replace;
    go.call(router, { path: "/", query });
  }

  const f = {
    q: computed(() => read("q")),
    status: computed(() => read("status")),
    triage: computed(() => read("triage")),
    type: computed(() => read("type")),
    fuel: computed(() => read("fuel")),
    project: computed(() => read("project")),
    area: computed(() => read("area")),
    office: computed(() => read("office")),
    dateType: computed(() => read("dateType")),
    from: computed(() => read("from")),
    to: computed(() => read("to")),
  };

  const sort = computed(() => (SORT_KEYS.includes(read("sort")) ? read("sort") : DEFAULTS.sort));
  const sortDir = computed(() => (read("dir") === "desc" ? -1 : 1));
  const view = computed(() => (VIEWS.includes(read("view")) ? read("view") : DEFAULTS.view));
  const openPlate = computed(() => read("vehicle"));
  const panelTab = computed(() =>
    PANEL_TABS.includes(read("vtab")) ? read("vtab") : DEFAULTS.vtab,
  );
  const alertsOpen = computed(() => read("alerts") === "1");

  const setFilter = (key, value) => write({ [key]: value });

  /* A pill and the triage chips toggle: pressing the one already applied clears it, which is
     what the reader means by pressing it a second time. */
  const toggleFilter = (key, value) => write({ [key]: f[key].value === value ? "" : value });

  function setSort(key) {
    if (sort.value === key) write({ dir: sortDir.value === 1 ? "desc" : "asc" });
    else write({ sort: key, dir: "asc" });
  }

  function setQuickDate(days) {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - days);
    write({ from: from.toISOString().split("T")[0], to: to.toISOString().split("T")[0] });
  }

  const clearDates = () => write({ from: "", to: "" });

  function resetFilters() {
    const patch = {};
    for (const key of FILTER_KEYS) patch[key] = "";
    write(patch);
  }

  const setView = (value) => write({ view: value }, { push: true });
  const openVehicle = (plate, tab = "overview") =>
    write({ vehicle: plate, vtab: tab }, { push: true });
  const closeVehicle = () => write({ vehicle: "", vtab: "" }, { push: true });
  const setPanelTab = (tab) => write({ vtab: tab });
  const setAlerts = (open) => write({ alerts: open ? "1" : "" }, { push: true });
  const toggleAlerts = () => setAlerts(!alertsOpen.value);

  const hasDateFilter = computed(() => Boolean(f.from.value || f.to.value));
  const anyFilterActive = computed(() =>
    FILTER_KEYS.some((key) => key !== "sort" && key !== "dir" && read(key) !== DEFAULTS[key]),
  );

  return {
    f,
    sort,
    sortDir,
    view,
    openPlate,
    panelTab,
    alertsOpen,
    hasDateFilter,
    anyFilterActive,
    setFilter,
    toggleFilter,
    setSort,
    setQuickDate,
    clearDates,
    resetFilters,
    setView,
    openVehicle,
    closeVehicle,
    setPanelTab,
    setAlerts,
    toggleAlerts,
  };
}
