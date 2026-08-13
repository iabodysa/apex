import { describe, expect, it } from "vitest";
import {
  buildHandoverPayload,
  inspectionRowsFromTemplate,
  isInspectionComplete,
} from "./handoverState.js";

describe("native vehicle handover state", () => {
  it("preserves every ordered template item and requires a remark for failures", () => {
    const rows = inspectionRowsFromTemplate([
      { check_item: "الإطارات", default_remark: "" },
      { check_item: "المصابيح", default_remark: "افحص الأمامي" },
    ]);
    rows[0].ok = true;
    rows[1].ok = false;
    expect(isInspectionComplete(rows)).toBe(false);
    rows[1].remark = "المصباح الأيسر لا يعمل";
    expect(isInspectionComplete(rows)).toBe(true);

    expect(buildHandoverPayload(
      { odometer: 12345, fuel_level: "Half", condition_notes: "", signed_evidence: "/private/files/signed.pdf" },
      { template: "VHC-1", items: [{ check_item: "الإطارات" }, { check_item: "المصابيح" }] },
      rows,
    )).toEqual({
      odometer: 12345,
      fuel_level: "Half",
      condition_notes: "",
      signed_evidence: "/private/files/signed.pdf",
      checklist_template: "VHC-1",
      inspection_rows: JSON.stringify([
        { check_item: "الإطارات", ok: 1, remark: "" },
        { check_item: "المصابيح", ok: 0, remark: "المصباح الأيسر لا يعمل" },
      ]),
    });
  });

  it("fails closed when the native template or signed evidence is missing", () => {
    expect(() => buildHandoverPayload(
      { odometer: 1, signed_evidence: "/signed.pdf" },
      null,
      [],
    )).toThrow("قالب");
    expect(() => buildHandoverPayload(
      { odometer: 1, signed_evidence: "" },
      { template: "VHC-1", items: [{ check_item: "الإطارات" }] },
      [{ check_item: "الإطارات", ok: true, remark: "" }],
    )).toThrow("الإثبات");
  });
});
