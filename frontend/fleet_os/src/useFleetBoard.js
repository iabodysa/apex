// Copyright (c) 2026, AFMCO and contributors
// The board's data model: fetch/normalize the scoped fleet and derive the summary
// counts + triage counts. Kept free of poll/realtime/panel concerns — the live-
// sync lifecycle is orchestrated in App.vue (it must read confirm/panel/selection
// /action state to know when to pause, so it belongs in the top-level shell).
import { ref, computed } from "vue";
import { call } from "./api.js";
import { normalize } from "./fleetHelpers.js";
import { resourceErrorMessage } from "./i18n.js";

const GET = "apex.salis.api.fleet_os.get_fleet_os";

export function useFleetBoard({ expiryFlag }) {
  const vehicles = ref([]);
  const loadState = ref("loading"); // loading | ready | error
  const loadError = ref("");
  // Typed empty reason from the API: scope_empty | data_empty | null.
  const loadReason = ref(null);
  // True when the most recent background re-pull failed and the board is showing
  // the last good list — surfaced as a non-blocking stale banner.
  const reloadStale = ref(false);

  async function loadFleet() {
    loadState.value = "loading";
    try {
      const r = await call(GET);
      vehicles.value = ((r && r.vehicles) || []).map(normalize);
      loadReason.value = (r && r.reason) || null;
      loadState.value = "ready";
    } catch (e) {
      loadError.value = resourceErrorMessage(e, "main.loadFailed");
      loadState.value = "error";
    }
  }
  // Background re-pull (after a write or a poll tick). Keeps the last good list on
  // failure and flags the board stale instead of swallowing the error. Panel
  // re-sync is done by the caller (App.vue) since panel state lives elsewhere.
  async function reloadFleet() {
    try {
      const r = await call(GET);
      vehicles.value = ((r && r.vehicles) || []).map(normalize);
      loadReason.value = (r && r.reason) || null;
      reloadStale.value = false;
    } catch (e) {
      // Console only, so the raw error object is the useful thing to log here.
      console.warn("[fleet] background reload failed:", e);
      reloadStale.value = true;
    }
  }

  const isScopeEmpty = computed(() => loadReason.value === "scope_empty");

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
  // Counts still resolving — drives the top-bar/sidebar shimmer so numbers don't
  // flash 0 before the first load lands.
  const countsLoading = computed(() => loadState.value === "loading");

  // Derived triage counts (vehicles with an open incident / nearing expiry).
  const triage = computed(() => {
    const all = vehicles.value;
    const hasOpenIncident = (v) =>
      (v.damages || []).some((d) => d.status !== "completed") ||
      (v.accidents || []).some((a) => a.status !== "closed");
    return {
      incidents: all.filter(hasOpenIncident).length,
      expiring: all.filter((v) => expiryFlag(v).show).length,
    };
  });

  return {
    vehicles, loadState, loadError, loadReason, reloadStale, isScopeEmpty,
    counts, countsLoading, triage,
    loadFleet, reloadFleet,
  };
}
