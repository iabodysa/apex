import { describe, expect, it } from "vitest";
import {
  cadenceLabel,
  dateTimeLabel,
  periodLabel,
  statusLabel,
  vehicleCategoryLabel,
} from "./displayLabels.js";

describe("portal display labels", () => {
  it("keeps stored workflow values while presenting Arabic labels", () => {
    expect(statusLabel("New")).toBe("جديد");
    expect(statusLabel("Completed")).toBe("مكتملة");
    expect(statusLabel("Dispatched")).toBe("في الطريق");
    expect(statusLabel("Unassigned")).toBe("غير مسندة");
    expect(statusLabel("assigned")).toBe("مسندة");
    expect(statusLabel("Custom State")).toBe("Custom State");
  });

  it("uses fleet terms familiar to Saudi operations teams", () => {
    expect(vehicleCategoryLabel("Coach")).toBe("حافلة");
    expect(vehicleCategoryLabel("Crew Van")).toBe("فان طاقم");
    expect(vehicleCategoryLabel("Custom Vehicle")).toBe("Custom Vehicle");
  });

  it("turns Frappe date and time values into concise Arabic business labels", () => {
    expect(dateTimeLabel("2026-08-13 13:46:08.944054")).toBe("13 أغسطس 2026، 1:46 م");
    expect(dateTimeLabel("13:46:9.167977")).toBe("1:46 م");
    expect(dateTimeLabel("")).toBe("");
  });

  it("renders structured safety periods instead of raw objects", () => {
    expect(cadenceLabel("Daily")).toBe("يومية");
    expect(periodLabel({ kind: "day" })).toBe("اليوم");
    expect(periodLabel({ kind: "quarter", quarter: 3, year: 2026 })).toBe("الربع 3 من 2026");
  });
});
