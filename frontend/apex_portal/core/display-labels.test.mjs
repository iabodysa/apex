import { describe, expect, it } from "vitest";
import { cadenceLabel, periodLabel, statusLabel } from "./displayLabels.js";

describe("portal display labels", () => {
  it("keeps stored workflow values while presenting Arabic labels", () => {
    expect(statusLabel("New")).toBe("جديد");
    expect(statusLabel("Completed")).toBe("مكتملة");
    expect(statusLabel("Custom State")).toBe("Custom State");
  });

  it("renders structured safety periods instead of raw objects", () => {
    expect(cadenceLabel("Daily")).toBe("يومية");
    expect(periodLabel({ kind: "day" })).toBe("اليوم");
    expect(periodLabel({ kind: "quarter", quarter: 3, year: 2026 })).toBe("الربع 3 من 2026");
  });
});
