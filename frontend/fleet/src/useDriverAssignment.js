// Copyright (c) 2026, AFMCO and contributors
// The assign/reassign-a-driver flow: the sub-form model, the server-backed driver
// picker (so reassign can never receive a free-typed id), and the optional
// Vehicle Handover capture. Assignment succeeds independently of the handover.
import { reactive } from "vue";
import { call } from "./api.js";
import { today, trim, serverMsg } from "./fleetHelpers.js";

const POST = (m) => "apex.salis.api.fleet_os." + m;

export function useDriverAssignment({ panel, subForm, showToast, cfShow, reloadFleet, t }) {
  // Reassign sub-form model. driverName = the canonical Salis Driver id sent to
  // reassign; date is the only other field sent. captureHandover (+ odometer /
  // checklistTemplate / conditionNotes) drive the OPTIONAL handover capture.
  const rf = reactive({
    driverName: "", driverLabel: "", date: today(),
    captureHandover: false, odometer: null, checklistTemplate: "", conditionNotes: "",
  });
  // Driver picker: query → results from search_drivers, with the chosen driver
  // pinned so reassign can never receive a free-typed (mis-resolvable) id.
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
      showToast(serverMsg(e), "red");
    } finally {
      dp.loading = false;
    }
  }
  function onDriverQuery() {
    // Picking a driver clears the pinned selection until a new one is chosen.
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
  // New driver create-or-assign: open the native Salis Driver Web Form in a new
  // tab (keeps the create path fully native — Web Form perms).
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
      // Optional handover: best-effort AFTER the assignment commits. A handover
      // failure is surfaced but never undoes the reassign (the capture is optional).
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
          showToast(t("toast.handoverFailed", { msg: serverMsg(e) }), "amber");
        }
      }
      subForm.value = null;
      await reloadFleet();
    } catch (e) {
      showToast(serverMsg(e), "red");
    }
  }

  return {
    rf, dp,
    resetReassign, runDriverSearch, onDriverQuery, pickDriver,
    openReassignForm, openNewDriverForm, submitReassign,
  };
}
