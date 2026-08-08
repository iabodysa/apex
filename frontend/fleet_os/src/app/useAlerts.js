// Copyright (c) 2026, afmcoltd
import { ref } from "vue";

import { getOpenAlerts } from "./api.js";
import { resourceErrorMessage } from "@/i18n";

export function useAlerts({ vehicles, t, openVehicle, closeAlerts }) {
  const alerts = ref([]);
  const alertTotal = ref(0);
  const alertsState = ref("idle");
  const alertsError = ref("");
  let issued = 0;

  /* Sequenced for the same reason the board is: the drawer, the poll and the realtime handler
     all start this read, and the older answer must not win. */
  async function loadAlerts() {
    if (alertsState.value !== "ready") alertsState.value = "loading";
    const ticket = ++issued;
    try {
      const res = await getOpenAlerts();
      if (ticket !== issued) return;
      alerts.value = (res && res.alerts) || [];
      alertTotal.value = (res && res.summary && res.summary.total) || 0;
      alertsState.value = "ready";
      alertsError.value = "";
    } catch (e) {
      if (ticket !== issued) return;
      alertsState.value = "error";
      alertsError.value = resourceErrorMessage(e, "alerts.loadError");
    }
  }

  const sevTheme = (s) => (s === "Critical" ? "red" : s === "Info" ? "green" : "orange");
  const sevLabel = (s) => t("alerts.sev" + (s || "Warning"));

  function alertVehicleOnBoard(a) {
    if (!a.vehicle_plate) return null;
    return vehicles.value.find((x) => x.plate === a.vehicle_plate) || null;
  }

  function openAlertTarget(a) {
    const v = alertVehicleOnBoard(a);
    if (v) {
      closeAlerts();
      openVehicle(v.plate);
      return;
    }
    window.open("/app/operations-alert/" + encodeURIComponent(a.name), "_blank", "noopener");
  }

  return {
    alerts,
    alertTotal,
    alertsState,
    alertsError,
    loadAlerts,
    sevTheme,
    sevLabel,
    alertVehicleOnBoard,
    openAlertTarget,
  };
}
