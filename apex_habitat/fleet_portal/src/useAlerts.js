// Copyright (c) 2026, AFMCO and contributors
// Operations-alert bell + drawer. The bell badge shows the scoped open-alert
// total; the drawer lists the rows. A row deep-links to its vehicle's panel when
// the plate is on the board, else opens the Operations Alert in Desk.
import { ref } from "vue";
import { call } from "./api.js";

const ALERTS_GET = "apex_habitat.salis.api.operations_alerts.get_open_alerts";

export function useAlerts({ vehicles, t, openPanel }) {
  const alerts = ref([]);
  const alertTotal = ref(0);
  const alertsState = ref("idle"); // idle | loading | ready | error
  const alertsOpen = ref(false);

  async function loadAlerts() {
    if (alertsState.value !== "ready") alertsState.value = "loading";
    try {
      const r = await call(ALERTS_GET);
      alerts.value = (r && r.alerts) || [];
      alertTotal.value = (r && r.summary && r.summary.total) || 0;
      alertsState.value = "ready";
    } catch (e) {
      alertsState.value = "error";
    }
  }
  function toggleAlerts() {
    alertsOpen.value = !alertsOpen.value;
    if (alertsOpen.value) loadAlerts();
  }
  function closeAlerts() {
    alertsOpen.value = false;
  }
  const sevClass = (s) =>
    s === "Critical" ? "alert-red" : s === "Info" ? "alert-green" : "alert-amber";
  const sevLabel = (s) => t("alerts.sev" + (s || "Warning"));

  // A row links to its vehicle's drawer if the plate is on the board; otherwise
  // to the Operations Alert record in Desk.
  function alertVehicleOnBoard(a) {
    if (!a.vehicle_plate) return null;
    return vehicles.value.find((x) => x.plate === a.vehicle_plate) || null;
  }
  function openAlertTarget(a) {
    const v = alertVehicleOnBoard(a);
    if (v) {
      closeAlerts();
      openPanel(v.plate);
    } else {
      window.open("/app/operations-alert/" + encodeURIComponent(a.name), "_blank");
    }
  }

  return {
    alerts, alertTotal, alertsState, alertsOpen,
    loadAlerts, toggleAlerts, closeAlerts,
    sevClass, sevLabel, alertVehicleOnBoard, openAlertTarget,
  };
}
