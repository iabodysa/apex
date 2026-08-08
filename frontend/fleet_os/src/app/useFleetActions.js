// Copyright (c) 2026, afmcoltd
import { reactive, ref } from "vue";

import {
  bulkStopVehicles,
  bulkWorkshopIn,
  recover,
  reportTheft,
  stopVehicle,
  workshopIn,
  workshopOut,
} from "./api.js";
import { statusKey, today, trim } from "./fleetHelpers.js";
import { resourceErrorMessage } from "@/i18n";

export function useFleetActions({
  vehicles,
  openVehicle,
  subForm,
  showToast,
  ask,
  reloadFleet,
  selected,
  clearSelection,
  openReassignForm,
  panelVehicle,
  t,
}) {
  const busyPlates = ref(new Set());
  const isBusy = (plate) => busyPlates.value.has(plate);
  function setBusy(plate, on) {
    const next = new Set(busyPlates.value);
    if (on) next.add(plate);
    else next.delete(plate);
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

  const fail = (e) => showToast(resourceErrorMessage(e, "errors.actionError"), "red");

  const sf = reactive({ date: today(), branch: "", reason: "", notes: "", nextStatus: "available" });
  function openStopForm(nextStatus = "available") {
    Object.assign(sf, { date: today(), branch: "", reason: "", notes: "", nextStatus });
    subForm.value = "stop";
  }

  /* Stopping and then choosing where the vehicle lands is two writes with no server-side
     transaction between them. If the second fails the vehicle IS stopped, so the message has
     to say which half went through — a bare "the action could not be completed" left the
     supervisor guessing, and the board reloads either way so the truth is on screen. */
  async function confirmStop() {
    const v = panelVehicle.value;
    if (!v || !v.current_driver) return;
    const driver = v.current_driver.name_ar || v.current_driver.name_en || t("logTab.driver");
    const ok = await ask({
      title: t("confirm.stopTitle"),
      message: t("confirm.stopMsg", { name: driver, plate: v.plate }),
      okLabel: t("confirm.stopOk"),
      theme: "red",
    });
    if (!ok) return;
    const reason = sf.notes ? `${sf.reason} — ${sf.notes}` : sf.reason;
    let stopped = false;
    try {
      await stopVehicle(v.plate, reason);
      stopped = true;
      if (sf.nextStatus === "workshop") await workshopIn(v.plate);
      else if (sf.nextStatus === "available") await recover(v.plate);
      const label = {
        available: t("toast.statusAvailable"),
        workshop: t("toast.statusWorkshop"),
        stopped: t("toast.statusStopped"),
      }[sf.nextStatus];
      showToast(t("toast.stopped", { status: label }), "green");
      subForm.value = null;
    } catch (e) {
      const detail = resourceErrorMessage(e, "errors.actionError");
      showToast(
        stopped ? t("toast.stoppedButNotMoved", { msg: detail }) : detail,
        stopped ? "amber" : "red",
      );
    } finally {
      await reloadFleet();
    }
  }

  const stf = reactive({ date: today(), police: "", location: "", reporter: "", desc: "", notes: "" });
  function openStolenForm() {
    Object.assign(stf, {
      date: today(),
      police: "",
      location: "",
      reporter: "",
      desc: "",
      notes: "",
    });
    subForm.value = "stolen";
  }
  async function submitStolen() {
    const v = panelVehicle.value;
    if (!v) return;
    const ok = await ask({
      title: t("confirm.stolenTitle"),
      message: t("confirm.stolenMsg", { plate: v.plate }),
      okLabel: t("confirm.stolenOk"),
      theme: "red",
    });
    if (!ok) return;
    try {
      await reportTheft(v.plate, trim(stf.location), trim(stf.police));
      showToast(t("toast.theftReported"), "amber");
      subForm.value = null;
      await reloadFleet();
    } catch (e) {
      fail(e);
    }
  }

  function quickStop(plate, goWorkshop = false) {
    openVehicle(plate, "driver");
    openStopForm(goWorkshop ? "workshop" : "available");
  }
  function quickReassign(plate) {
    openVehicle(plate, "driver");
    openReassignForm();
  }
  function markStolen(plate) {
    openVehicle(plate, "status");
    openStolenForm();
  }

  const find = (plate) => vehicles.value.find((x) => x.plate === plate);

  async function sendWorkshop(plate) {
    const v = find(plate);
    if (!v) return;
    if (v.current_driver) {
      showToast(t("toast.stopBeforeWorkshop"), "amber");
      return;
    }
    const ok = await ask({
      title: t("confirm.sendWorkshopTitle"),
      message: t("confirm.sendWorkshopMsg", { plate }),
      okLabel: t("confirm.sendWorkshopOk"),
      theme: "gray",
    });
    if (!ok) return;
    await runCardAction(plate, async () => {
      try {
        await workshopIn(plate);
        showToast(t("toast.sentToWorkshop"), "amber");
        await reloadFleet();
      } catch (e) {
        fail(e);
      }
    });
  }

  async function exitWorkshop(plate) {
    if (!find(plate)) return;
    const ok = await ask({
      title: t("confirm.exitWorkshopTitle"),
      message: t("confirm.exitWorkshopMsg", { plate }),
      okLabel: t("confirm.exitWorkshopOk"),
      theme: "green",
    });
    if (!ok) return;
    await runCardAction(plate, async () => {
      try {
        await workshopOut(plate);
        showToast(t("toast.leftWorkshop"), "green");
        await reloadFleet();
      } catch (e) {
        fail(e);
      }
    });
  }

  async function setAvailable(plate) {
    if (!find(plate)) return;
    const ok = await ask({
      title: t("confirm.setAvailableTitle"),
      message: t("confirm.setAvailableMsg", { plate }),
      okLabel: t("confirm.ok"),
      theme: "green",
    });
    if (!ok) return;
    await runCardAction(plate, async () => {
      try {
        await recover(plate);
        showToast(t("toast.availableAtOffice"), "green");
        await reloadFleet();
      } catch (e) {
        fail(e);
      }
    });
  }

  async function recoverVehicle(plate) {
    if (!find(plate)) return;
    const ok = await ask({
      title: t("confirm.recoverTitle"),
      message: t("confirm.recoverMsg", { plate }),
      okLabel: t("confirm.recoverOk"),
      theme: "green",
    });
    if (!ok) return;
    await runCardAction(plate, async () => {
      try {
        await recover(plate);
        showToast(t("toast.recovered"), "green");
        await reloadFleet();
      } catch (e) {
        fail(e);
      }
    });
  }

  const bulkNote = ref("");
  function showBulkSummary(res) {
    const r = res || {};
    showToast(
      t("bulk.summary", { ok: r.succeeded || 0, failed: r.failed || 0 }),
      (r.failed || 0) > 0 ? "amber" : "green",
    );
  }

  async function runBulk({ titleKey, okKey, request }) {
    const plates = [...selected.value];
    if (!plates.length) return;
    const ok = await ask({
      title: t(titleKey),
      message: t("bulk.selected", { n: plates.length }),
      okLabel: t(okKey),
      theme: "red",
    });
    if (!ok) return;
    try {
      showBulkSummary(await request(plates, trim(bulkNote.value)));
      bulkNote.value = "";
      clearSelection();
      await reloadFleet();
    } catch (e) {
      fail(e);
    }
  }

  const bulkStop = () =>
    runBulk({
      titleKey: "confirm.stopTitle",
      okKey: "bulk.stopSelected",
      request: bulkStopVehicles,
    });
  const bulkWorkshop = () =>
    runBulk({
      titleKey: "confirm.sendWorkshopTitle",
      okKey: "bulk.workshopSelected",
      request: bulkWorkshopIn,
    });

  async function changeStatus(plate, newStatus) {
    const v = find(plate);
    if (!v || newStatus === v.vehicle_status) return;
    if (newStatus === "assigned") {
      openReassignForm();
      return;
    }
    if (v.current_driver) {
      showToast(t("toast.stopCurrentFirst"), "amber");
      return;
    }
    if (newStatus === "stolen") {
      openStolenForm();
      return;
    }
    if (v.vehicle_status === "stolen") {
      await recoverVehicle(plate);
      return;
    }
    const ok = await ask({
      title: t("confirm.changeStatusTitle"),
      message: t("confirm.changeStatusMsg", {
        plate,
        from: t("status." + statusKey(v.vehicle_status)),
        to: t("status." + statusKey(newStatus)),
      }),
      okLabel: t("confirm.changeStatusOk"),
      theme: "gray",
    });
    if (!ok) return;
    const wasWorkshop = v.vehicle_status === "workshop";
    try {
      if (newStatus === "workshop") await workshopIn(plate);
      else if (newStatus === "available") await (wasWorkshop ? workshopOut(plate) : recover(plate));
      else if (newStatus === "stopped") await stopVehicle(plate, "");
      showToast(t("toast.statusUpdated"), "green");
      await reloadFleet();
    } catch (e) {
      fail(e);
    }
  }

  return {
    busyPlates,
    isBusy,
    sf,
    openStopForm,
    confirmStop,
    stf,
    openStolenForm,
    submitStolen,
    quickStop,
    quickReassign,
    sendWorkshop,
    exitWorkshop,
    setAvailable,
    recoverVehicle,
    markStolen,
    bulkNote,
    bulkStop,
    bulkWorkshop,
    changeStatus,
  };
}
