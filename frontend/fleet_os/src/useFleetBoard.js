// Copyright (c) 2026, afmcoltd
import { ref, computed } from "vue";
import { call } from "./api.js";
import { normalize } from "./fleetHelpers.js";
import { resourceErrorMessage } from "./i18n.js";

const GET = "apex.salis.api.fleet_os.get_fleet_os";

export function useFleetBoard({ expiryFlag }) {
  const vehicles = ref([]);
  const loadState = ref("loading");
  const loadError = ref("");
  const loadReason = ref(null);
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
  async function reloadFleet() {
    try {
      const r = await call(GET);
      vehicles.value = ((r && r.vehicles) || []).map(normalize);
      loadReason.value = (r && r.reason) || null;
      reloadStale.value = false;
    } catch (e) {
      console.warn("[fleet] background reload failed:", e);
      reloadStale.value = true;
    }
  }

  const isScopeEmpty = computed(() => loadReason.value === "scope_empty");

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
  const countsLoading = computed(() => loadState.value === "loading");

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
