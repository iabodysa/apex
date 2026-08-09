// Copyright (c) 2026, afmcoltd
import { computed, ref } from "vue";

import { getFleetOs } from "./api.js";
import { hasOpenIncident, normalize, normalizeReaderErrors } from "./fleetHelpers.js";
import { resourceErrorMessage } from "@/i18n";

export function useFleetBoard({ expiryFlag }) {
  const vehicles = ref([]);
  const loadState = ref("loading");
  const loadError = ref("");
  const loadReason = ref(null);
  const readerErrors = ref([]);
  const reloadStale = ref(false);
  let issued = 0;

  /* Mount, the 30 s poll, the realtime handler and the return-to-tab all reach this one
     function, so two reads can easily be in flight together. The ticket is what stops the
     older answer landing last and painting a board that is already out of date. */
  async function fetchBoard({ background }) {
    if (!background) loadState.value = "loading";
    const ticket = ++issued;
    try {
      const res = await getFleetOs();
      if (ticket !== issued) return;
      vehicles.value = ((res && res.vehicles) || []).map(normalize);
      loadReason.value = (res && res.reason) || null;
      /* The server reports which enrichment readers failed so a board that loaded with a
         section missing does not look identical to one that loaded whole. */
      readerErrors.value = normalizeReaderErrors(res && res.reader_errors);
      loadState.value = "ready";
      loadError.value = "";
      reloadStale.value = false;
    } catch (e) {
      if (ticket !== issued) return;
      if (background) {
        /* Keep the last good board on screen and say it is old, rather than blanking a screen
           the supervisor is mid-decision on. */
        reloadStale.value = true;
        return;
      }
      loadError.value = resourceErrorMessage(e, "main.loadFailed");
      loadState.value = "error";
    }
  }

  const loadFleet = () => fetchBoard({ background: false });
  const reloadFleet = () => fetchBoard({ background: true });

  const isScopeEmpty = computed(() => loadReason.value === "scope_empty");

  const counts = computed(() => {
    const all = vehicles.value;
    const by = (s) => all.filter((v) => v.vehicle_status === s).length;
    const drivers = new Set(
      all.flatMap((v) => v.history.map((h) => h.driver_id)).filter(Boolean),
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

  const triage = computed(() => ({
    incidents: vehicles.value.filter(hasOpenIncident).length,
    expiring: vehicles.value.filter((v) => expiryFlag(v).show).length,
    workshop: vehicles.value.filter((v) => v.workshop_overstay === true).length,
  }));

  return {
    vehicles,
    loadState,
    loadError,
    loadReason,
    readerErrors,
    reloadStale,
    isScopeEmpty,
    counts,
    countsLoading,
    triage,
    loadFleet,
    reloadFleet,
  };
}
