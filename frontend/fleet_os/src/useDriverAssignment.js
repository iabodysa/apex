// Copyright (c) 2026, afmcoltd
import { reactive, ref } from "vue";

import { createHandover, reassign, searchDrivers } from "./api.js";
import { today, trim } from "./fleetHelpers.js";
import { resourceErrorMessage } from "@/i18n";

export function useDriverAssignment({
  subForm,
  showToast,
  ask,
  reloadFleet,
  panelVehicle,
  t,
}) {
  const rf = reactive({
    driverName: "",
    driverLabel: "",
    date: today(),
    captureHandover: false,
    odometer: null,
    checklistTemplate: "",
    conditionNotes: "",
  });
  const driverOptions = ref([]);
  const driverLoading = ref(false);
  const handoverMissing = ref(false);
  let searchTimer = null;
  let issued = 0;

  function resetReassign() {
    Object.assign(rf, {
      driverName: "",
      driverLabel: "",
      date: today(),
      captureHandover: false,
      odometer: null,
      checklistTemplate: "",
      conditionNotes: "",
    });
    driverOptions.value = [];
    handoverMissing.value = false;
  }

  async function runSearch(query) {
    driverLoading.value = true;
    const ticket = ++issued;
    try {
      const rows = (await searchDrivers(trim(query))) || [];
      if (ticket !== issued) return;
      driverOptions.value = rows.map((d) => ({
        label: d.full_name || d.name,
        value: d.name,
        description: [d.driver_id, d.phone].filter(Boolean).join(" · "),
      }));
    } catch (e) {
      if (ticket !== issued) return;
      driverOptions.value = [];
      showToast(resourceErrorMessage(e, "errors.loadError"), "red");
    } finally {
      if (ticket === issued) driverLoading.value = false;
    }
  }

  function onDriverQuery(query) {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => runSearch(query), 250);
  }

  function pickDriver(option) {
    rf.driverName = option ? option.value : "";
    rf.driverLabel = option ? option.label : "";
  }

  function openReassignForm() {
    resetReassign();
    subForm.value = "reassign";
  }

  function openNewDriverForm() {
    window.open("/salis-driver", "_blank", "noopener");
  }

  async function submitReassign() {
    const v = panelVehicle.value;
    if (!v) return;
    if (!rf.driverName) {
      showToast(t("toast.pickDriverRequired"), "amber");
      return;
    }
    const ok = await ask({
      title: t("confirm.reassignTitle"),
      message: t("confirm.reassignMsg", { name: rf.driverLabel, plate: v.plate }),
      okLabel: t("confirm.reassignOk"),
      theme: "green",
    });
    if (!ok) return;
    try {
      await reassign(v.plate, rf.driverName, rf.date || today());
      showToast(t("toast.reassigned", { name: rf.driverLabel, plate: v.plate }), "green");
      handoverMissing.value = false;
      if (rf.captureHandover) {
        try {
          const res = await createHandover({
            plate: v.plate,
            driver_id: rf.driverName,
            date: rf.date || today(),
            odometer: rf.odometer,
            checklist_template: trim(rf.checklistTemplate),
            condition_notes: rf.conditionNotes,
          });
          if (res && res.handover) {
            showToast(t("toast.handoverDrafted", { name: res.handover }), "green");
          } else {
            showToast(t("toast.handoverSkipped"), "green");
          }
        } catch (e) {
          handoverMissing.value = true;
          showToast(
            t("toast.handoverFailed", { msg: resourceErrorMessage(e, "errors.actionError") }),
            "amber",
          );
        }
      }
      if (!handoverMissing.value) subForm.value = null;
      await reloadFleet();
    } catch (e) {
      showToast(resourceErrorMessage(e, "errors.actionError"), "red");
    }
  }

  return {
    rf,
    driverOptions,
    driverLoading,
    handoverMissing,
    onDriverQuery,
    pickDriver,
    openReassignForm,
    openNewDriverForm,
    submitReassign,
  };
}
