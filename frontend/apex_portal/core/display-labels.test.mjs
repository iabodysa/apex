import { describe, expect, it } from "vitest";
import {
  cadenceLabel,
  conditionLabel,
  dateTimeLabel,
  floorLabel,
  humanLabel,
  humanOptions,
  recordTitle,
  remainingSeconds,
  periodLabel,
  statusLabel,
  statusOptions,
  statusTheme,
  vehicleCategoryLabel,
} from "./displayLabels.js";

describe("portal display labels", () => {
  it("keeps stored workflow values while presenting Arabic labels", () => {
    expect(statusLabel("New")).toBe("جديد");
    expect(statusLabel("Completed")).toBe("مكتملة");
    expect(statusLabel("Dispatched")).toBe("في الطريق");
    expect(statusLabel("Boarded")).toBe("صعد");
    expect(statusLabel("Validated")).toBe("تم التحقق");
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
    expect(statusLabel("scheduled")).toBe("الرحلة مجدولة");
    expect(statusLabel("en_route")).toBe("الحافلة في الطريق");
    expect(statusLabel("Custom State")).toBe("Custom State");
  });

  it("builds shared status and Link options with human labels as the primary text", () => {
    expect(statusOptions(["Planned", "Dispatched", "Completed"])).toEqual([
      { value: "Planned", label: "مجدولة" },
      { value: "Dispatched", label: "في الطريق" },
      { value: "Completed", label: "مكتملة" },
    ]);
    const project = { project: "PROJ-001", project_label: "مشروع المطار" };
    expect(humanLabel(project, "project", "project_label", "غير محدد")).toBe("مشروع المطار");
    expect(humanOptions([project, project], "project", "project_label")).toEqual([
      { value: "PROJ-001", label: "مشروع المطار" },
    ]);
  });

  it("maps workflow meaning to native frappe-ui badge themes", () => {
    expect(statusTheme("Completed")).toBe("green");
    expect(statusTheme("Approved")).toBe("green");
    expect(statusTheme("Pending")).toBe("orange");
    expect(statusTheme("Open")).toBe("orange");
    expect(statusTheme("Failed")).toBe("red");
    expect(statusTheme("Rejected")).toBe("red");
    expect(statusTheme("Draft")).toBe("gray");
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

  it("renders inventory conditions in the language of the housing task", () => {
    expect(conditionLabel("Good")).toBe("جيدة");
    expect(conditionLabel("Needs Maintenance")).toBe("تحتاج صيانة");
    expect(conditionLabel("Missing")).toBe("مفقودة");
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

  it("uses configured human fields and never promotes a naming-series id to the title", () => {
    expect(recordTitle(
      { name: "TR-2026-00042", requester_name: "محمد سالم", service_line: "سكن إلى مشروع" },
      ["requester_name", "service_line"],
      "طلب نقل",
    )).toBe("محمد سالم");
    expect(recordTitle(
      { name: "DT-2026-00007", route_name: "رحلة الوردية الصباحية" },
      ["route_name", "shift_name"],
      "رحلة",
    )).toBe("رحلة الوردية الصباحية");
    expect(recordTitle({ name: "DT-2026-00007" }, ["route_name"], "رحلة")).toBe("رحلة");
  });
});
