import { describe, expect, it } from "vitest";
import {
  cadenceLabel,
  dateTimeLabel,
  floorLabel,
  remainingSeconds,
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
    expect(statusLabel("Ready")).toBe("جاهزة");
    expect(statusLabel("Needs Cleaning")).toBe("تحتاج تنظيف");
    expect(statusLabel("Occupied")).toBe("مشغول");
    expect(statusLabel("Good")).toBe("جيدة");
    expect(statusLabel("Not Done")).toBe("لم تُنفذ");
    expect(statusLabel("High")).toBe("عالية");
    expect(statusLabel("Active")).toBe("نشط");
    expect(statusLabel("Exhausted")).toBe("مستنفد");
    expect(statusLabel("Closed")).toBe("مغلق");
    expect(statusLabel("Unknown")).toBe("غير معروف");
    expect(statusLabel("Scrapped")).toBe("مستبعد");
    expect(statusLabel("In Progress")).toBe("قيد التنفيذ");
    expect(statusLabel("Under Maintenance")).toBe("تحت الصيانة");
    expect(statusLabel("Not Tracked")).toBe("غير متابع");
    expect(statusLabel("Standard")).toBe("عادي");
    expect(statusLabel("Custom State")).toBe("Custom State");
  });

  it("localizes generated floor labels without changing custom names", () => {
    expect(floorLabel("Floor 1")).toBe("الطابق 1");
    expect(floorLabel("الميزانين")).toBe("الميزانين");
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

  it("calculates live windows from Frappe datetimes in Riyadh time", () => {
    const now = Date.parse("2026-08-13T10:00:30Z");
    expect(remainingSeconds("2026-08-13 13:00:00", 120, now)).toBe(90);
    expect(remainingSeconds("2026-08-13 12:58:00", 60, now)).toBe(0);
    expect(remainingSeconds(null, 60, now)).toBeNull();
  });

  it("renders structured safety periods instead of raw objects", () => {
    expect(cadenceLabel("Daily")).toBe("يومية");
    expect(periodLabel({ kind: "day" })).toBe("اليوم");
    expect(periodLabel({ kind: "quarter", quarter: 3, year: 2026 })).toBe("الربع 3 من 2026");
  });
});
