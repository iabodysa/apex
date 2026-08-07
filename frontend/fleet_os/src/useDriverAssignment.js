// Copyright (c) 2026, afmcoltd
import { reactive } from "vue";
import { call } from "./api.js";
import { today, trim } from "./fleetHelpers.js";
import { resourceErrorMessage } from "./i18n.js";

const POST = (m) => "apex.salis.api.fleet_os." + m;

export function useDriverAssignment({ panel, subForm, showToast, cfShow, reloadFleet, t }) {
  const rf = reactive({
    driverName: "", driverLabel: "", date: today(),
    captureHandover: false, odometer: null, checklistTemplate: "", conditionNotes: "",
  });
  const dp = reactive({ query: "", results: [], open: false, loading: false });
  let dpTimer = null;

  function resetReassign() {
    Object.assign(rf, {
      driverName: "", driverLabel: "", date: today(),
      captureHandover: false, odometer: null, checklistTemplate: "", conditionNotes: "",
    });
    Object.assign(dp, { query: "", results: [], open: false, loading: false });
  }
  async function runDriverSearch() {
    dp.loading = true;
    try {
      dp.results = (await call(POST("search_drivers"), { type: "GET", args: { q: trim(dp.query) } })) || [];
      dp.open = true;
    } catch (e) {
      dp.results = [];
      showToast(resourceErrorMessage(e, "errors.loadError"), "red");
    } finally {
      dp.loading = false;
    }
  }
  function onDriverQuery() {
    rf.driverName = "";
    rf.driverLabel = "";
    clearTimeout(dpTimer);
    dpTimer = setTimeout(runDriverSearch, 250);
  }
  function pickDriver(d) {
    rf.driverName = d.name;
    rf.driverLabel = d.full_name || d.driver_id || d.name;
    dp.query = rf.driverLabel + (d.driver_id ? " — " + d.driver_id : "");
    dp.open = false;
  }
  function openReassignForm() {
    resetReassign();
    subForm.value = "reassign";
  }
  function openNewDriverForm() {
    window.open("/salis-driver", "_blank", "noopener");
  }
  async function submitReassign() {
    const v = panel.vehicle;
    if (!v) return;
    if (!rf.driverName) {
      showToast(t("toast.pickDriverRequired"), "amber");
      return;
    }
    const ok = await cfShow(
      t("confirm.reassignTitle"),
      t("confirm.reassignMsg", { name: rf.driverLabel, plate: v.plate }),
      "lock",
      t("confirm.reassignOk"),
      "btn-green"
    );
    if (!ok) return;
    try {
      await call(POST("reassign"), {
        type: "POST",
        args: { plate: v.plate, driver_id: rf.driverName, date: rf.date || today() },
      });
      showToast(t("toast.reassigned", { name: rf.driverLabel, plate: v.plate }), "green");
      if (rf.captureHandover) {
        try {
          const res = await call(POST("create_handover"), {
            type: "POST",
            args: {
              plate: v.plate,
              driver_id: rf.driverName,
              date: rf.date || today(),
              odometer: rf.odometer,
              checklist_template: trim(rf.checklistTemplate),
              condition_notes: rf.conditionNotes,
            },
          });
          if (res && res.handover) {
            showToast(t("toast.handoverDrafted", { name: res.handover }), "green");
          } else {
            showToast(t("toast.handoverSkipped"), "green");
          }
        } catch (e) {
          showToast(t("toast.handoverFailed", { msg: resourceErrorMessage(e, "errors.actionError") }), "amber");
        }
      }
      subForm.value = null;
      await reloadFleet();
    } catch (e) {
      showToast(resourceErrorMessage(e, "errors.actionError"), "red");
    }
  }

  return {
    rf, dp,
    resetReassign, runDriverSearch, onDriverQuery, pickDriver,
    openReassignForm, openNewDriverForm, submitReassign,
  };
}
