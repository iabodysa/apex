// Copyright (c) 2026, AFMCO and contributors
// Every write action on the board that isn't the assign/reassign flow: the
// stop/stolen sub-forms, the quick card actions, the status-picker transitions,
// and the bulk endpoints. Each card action is guarded against double-submit via
// per-plate busy tracking. Depends on the panel, confirm, toast, selection, and
// (for status → assign) the driver-assignment flow, all injected.
import { reactive, ref } from "vue";
import { call } from "./api.js";
import { today, trim, statusKey, serverMsg } from "./fleetHelpers.js";

const POST = (m) => "apex.salis.api.fleet_os." + m;

export function useFleetActions({
  vehicles, panel, subForm, openPanel,
  showToast, cfShow, reloadFleet,
  selected, clearSelection, openReassignForm, t,
}) {
  // In-flight direct-POST card actions, keyed by plate. While a plate is busy its
  // card buttons disable + show a spinner so a slow POST can't be double-fired.
  const busyPlates = ref(new Set());
  const isBusy = (plate) => busyPlates.value.has(plate);
  function setBusy(plate, on) {
    const next = new Set(busyPlates.value);
    on ? next.add(plate) : next.delete(plate);
    busyPlates.value = next;
  }
  async function runCardAction(plate, fn) {
    if (isBusy(plate)) return;
    setBusy(plate, true);
    try {
      await fn();
    } finally {
      setBusy(plate, false);
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
    await runCardAction(plate, async () => {
      try {
        await call(POST("workshop_in"), { type: "POST", args: { plate } });
        showToast(t("toast.sentToWorkshop"), "amber");
        await reloadFleet();
      } catch (e) {
        showToast(serverMsg(e), "red");
      }
    });
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
    await runCardAction(plate, async () => {
      try {
        await call(POST("workshop_out"), { type: "POST", args: { plate } });
        showToast(t("toast.leftWorkshop"), "green");
        await reloadFleet();
      } catch (e) {
        showToast(serverMsg(e), "red");
      }
    });
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
    await runCardAction(plate, async () => {
      try {
        await call(POST("recover"), { type: "POST", args: { plate } });
        showToast(t("toast.availableAtOffice"), "green");
        await reloadFleet();
      } catch (e) {
        showToast(serverMsg(e), "red");
      }
    });
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
    await runCardAction(plate, async () => {
      try {
        await call(POST("recover"), { type: "POST", args: { plate } });
        showToast(t("toast.recovered"), "green");
        await reloadFleet();
      } catch (e) {
        showToast(serverMsg(e), "red");
      }
    });
  }
  function markStolen(plate) {
    openPanel(plate, 2);
    openStolenForm();
  }

  // ── Bulk actions → bulk endpoints ──
  // One free-text note feeds the matching arg (reason for stop / notes for
  // workshop), mirroring the single-vehicle reason/notes inputs.
  const bulkNote = ref("");
  const selectedPlates = () => Array.from(selected.value);
  function showBulkSummary(res) {
    const r = res || {};
    const type = (r.failed || 0) > 0 ? "amber" : "green";
    showToast(t("bulk.summary", { ok: r.succeeded || 0, failed: r.failed || 0 }), type);
  }
  async function bulkStop() {
    const plates = selectedPlates();
    if (!plates.length) return;
    const ok = await cfShow(
      t("confirm.stopTitle"),
      t("bulk.selected", { n: plates.length }),
      "circle-pause",
      t("bulk.stopSelected"),
      "btn-red"
    );
    if (!ok) return;
    try {
      const res = await call(POST("bulk_stop_vehicles"), {
        type: "POST",
        args: { plates, reason: trim(bulkNote.value) },
      });
      showBulkSummary(res);
      bulkNote.value = "";
      clearSelection();
      await reloadFleet();
    } catch (e) {
      showToast(serverMsg(e), "red");
    }
  }
  async function bulkWorkshop() {
    const plates = selectedPlates();
    if (!plates.length) return;
    const ok = await cfShow(
      t("confirm.sendWorkshopTitle"),
      t("bulk.selected", { n: plates.length }),
      "wrench",
      t("bulk.workshopSelected"),
      "btn-amber"
    );
    if (!ok) return;
    try {
      const res = await call(POST("bulk_workshop_in"), {
        type: "POST",
        args: { plates, notes: trim(bulkNote.value) },
      });
      showBulkSummary(res);
      bulkNote.value = "";
      clearSelection();
      await reloadFleet();
    } catch (e) {
      showToast(serverMsg(e), "red");
    }
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

  return {
    busyPlates, isBusy,
    sf, openStopForm, confirmStop,
    stf, openStolenForm, submitStolen,
    quickStop, quickReassign, sendWorkshop, exitWorkshop, setAvailable, recoverVehicle, markStolen,
    bulkNote, bulkStop, bulkWorkshop,
    changeStatus,
  };
}
