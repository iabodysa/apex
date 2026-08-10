// Copyright (c) 2026, afmcoltd
import { computed } from "vue";

import { calcTotalDaysNum, hasOpenIncident, trim } from "./fleetHelpers.js";

export function useFleetFilters({ vehicles, board, fmt, t }) {
  const { f, sort, sortDir } = board;
  const { expiryFlag, statusKey } = fmt;

  const filtered = computed(() => {
    const q = f.q.value.toLowerCase();
    const list = vehicles.value.filter((v) => {
      if (f.triage.value === "incidents" && !hasOpenIncident(v)) return false;
      if (f.triage.value === "expiring" && !expiryFlag(v).show) return false;
      if (f.triage.value === "workshop" && v.workshop_overstay !== true) return false;
      if (f.status.value && v.vehicle_status !== f.status.value) return false;
      if (f.type.value && v.sheet !== f.type.value) return false;
      if (f.fuel.value && !(v.fuel || "").includes(f.fuel.value)) return false;
      if (f.project.value && trim(v.project) !== f.project.value) return false;
      if (f.area.value && trim(v.area) !== f.area.value) return false;
      if (f.office.value && trim(v.rental_office) !== f.office.value) return false;
      if (q) {
        const d = v.current_driver;
        const hay = [
          v.plate,
          v.vehicle_type,
          v.rental_office,
          v.area,
          d ? d.name_ar : "",
          d ? d.name_en : "",
          d ? d.driver_id : "",
        ]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (f.from.value || f.to.value) {
        const match = v.history.some((h) => {
          let dates;
          if (f.dateType.value === "receive") dates = [h.date_receive];
          else if (f.dateType.value === "deliver") dates = [h.date_deliver];
          else dates = [h.date_receive, h.date_deliver];
          return dates.some((d) => {
            if (!d) return false;
            if (f.from.value && d < f.from.value) return false;
            if (f.to.value && d > f.to.value) return false;
            return true;
          });
        });
        if (!match) return false;
      }
      return true;
    });

    const key = sort.value === "status" ? "vehicle_status" : sort.value;
    return list.slice().sort((a, b) => {
      if (key === "drivers_desc") return (b.history.length - a.history.length) * sortDir.value;
      if (key === "duration_desc") {
        return (calcTotalDaysNum(b) - calcTotalDaysNum(a)) * sortDir.value;
      }
      return (a[key] || "").toString().localeCompare((b[key] || "").toString(), "ar") * sortDir.value;
    });
  });

  const driverGroups = computed(() => {
    const byDriver = new Map();
    const unassigned = [];
    for (const v of filtered.value) {
      const d = v.current_driver;
      if (!d) {
        unassigned.push(v);
        continue;
      }
      const key = d.driver_id || d.name_en || d.name_ar || v.plate;
      if (!byDriver.has(key)) byDriver.set(key, { key, driver: d, vehicles: [] });
      byDriver.get(key).vehicles.push(v);
    }
    const groups = [...byDriver.values()].sort((a, b) =>
      (a.driver.name_ar || a.driver.name_en || "").localeCompare(
        b.driver.name_ar || b.driver.name_en || "",
        "ar",
      ),
    );
    if (unassigned.length) groups.push({ key: "__unassigned__", driver: null, vehicles: unassigned });
    return groups;
  });

  const optionsFrom = (key) =>
    computed(() =>
      [...new Set((vehicles.value || []).map((v) => trim(v[key])).filter(Boolean))]
        .sort((a, b) => a.localeCompare(b, "ar"))
        .map((value) => ({ label: value, value })),
    );
  const projectOptions = optionsFrom("project");
  const areaOptions = optionsFrom("area");
  const officeOptions = optionsFrom("rental_office");

  const dateInfo = computed(() => {
    if (!board.hasDateFilter.value) return "";
    const typeKey = { receive: "receive", deliver: "deliver", any: "anyDate" }[f.dateType.value];
    return t("dateInfo.summary", {
      n: filtered.value.length,
      type: t("sidebar." + typeKey),
      from: f.from.value || "…",
      to: f.to.value || t("common.today"),
    });
  });

  const activeFilterChips = computed(() => {
    const chips = [];
    if (f.q.value) chips.push(t("chip.search", { v: f.q.value }));
    if (f.status.value) {
      chips.push(t("chip.status", { v: t("status." + statusKey(f.status.value)) }));
    }
    if (f.type.value) chips.push(t("chip.type", { v: f.type.value }));
    if (f.fuel.value) chips.push(t("chip.fuel", { v: f.fuel.value }));
    if (f.project.value) chips.push(t("chip.project", { v: f.project.value }));
    if (f.area.value) chips.push(t("chip.area", { v: f.area.value }));
    if (f.office.value) chips.push(t("chip.office", { v: f.office.value }));
    if (f.from.value || f.to.value) {
      chips.push(
        t("chip.date", { from: f.from.value || "…", to: f.to.value || t("common.today") }),
      );
    }
    return chips;
  });

  return {
    filtered,
    driverGroups,
    projectOptions,
    areaOptions,
    officeOptions,
    dateInfo,
    activeFilterChips,
  };
}
