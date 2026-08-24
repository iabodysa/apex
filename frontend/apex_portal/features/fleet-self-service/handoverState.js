import { __ } from "../../core/i18n.js";

export function inspectionRowsFromTemplate(items) {
  return (items || []).map((item) => ({
    check_item: String(item?.check_item || "").trim(),
    ok: null,
    default_remark: String(item?.default_remark || ""),
    remark: "",
  }));
}

export function isInspectionComplete(rows) {
  return Boolean(rows?.length) && rows.every((row) => (
    typeof row.ok === "boolean" && (row.ok || String(row.remark || "").trim())
  ));
}

export function buildHandoverPayload(form, checklist, rows) {
  if (!checklist?.template || !Array.isArray(checklist.items) || !checklist.items.length) {
    throw new Error(__("No active inspection template exists for this operation."));
  }
  if (!checklist.assignment) {
    throw new Error(__("Could not link the inspection to the vehicle custody. Reload the page."));
  }
  if (!form?.signed_evidence) {
    throw new Error(__("Attach the signed evidence before confirming."));
  }
  const odometer = Number(form.odometer);
  if (form.odometer === "" || form.odometer === null || form.odometer === undefined
    || !Number.isFinite(odometer) || odometer < 0) {
    throw new Error(__("Enter a valid odometer reading."));
  }
  if (rows?.length !== checklist.items.length || !isInspectionComplete(rows)) {
    throw new Error(__("Complete the result for every item and add a note for every item that is not OK."));
  }
  const inspectionRows = rows.map((row, index) => {
    const expected = String(checklist.items[index]?.check_item || "").trim();
    if (!expected || row.check_item !== expected) {
      throw new Error(__("The inspection template changed. Reload the page before continuing."));
    }
    return {
      check_item: row.check_item,
      ok: row.ok ? 1 : 0,
      remark: String(row.remark || "").trim(),
    };
  });
  return {
    assignment: checklist.assignment,
    odometer,
    fuel_level: form.fuel_level || "",
    condition_notes: form.condition_notes || "",
    signed_evidence: form.signed_evidence,
    checklist_template: checklist.template,
    inspection_rows: JSON.stringify(inspectionRows),
  };
}
