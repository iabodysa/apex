import { describe, expect, it } from "vitest";
import { filtersFromQuery, queryFromFilters, resultCountLabel } from "./queueState.js";

describe("supervisor queue URL state", () => {
  it("builds task filters without dropping the queue base filter", () => {
    expect(filtersFromQuery({
      status: "Approved",
      project: "PROJ-1",
      date: "2026-08-14",
    }, {
      base: { docstatus: ["<", 2] },
      dateField: "pickup_datetime",
    })).toEqual({
      docstatus: ["<", 2],
      status: "Approved",
      project: "PROJ-1",
      pickup_datetime: ["between", ["2026-08-14 00:00:00", "2026-08-14 23:59:59"]],
    });
  });

  it("keeps only meaningful filter values in the URL", () => {
    expect(queryFromFilters({ status: "Planned", project: "", date: "2026-08-14" }))
      .toEqual({ status: "Planned", date: "2026-08-14" });
  });

  it("reports the loaded result count and whether more records are available", () => {
    expect(resultCountLabel(20, true)).toBe("20 نتيجة مع نتائج إضافية");
    expect(resultCountLabel(7, false)).toBe("7 نتائج");
  });
});
