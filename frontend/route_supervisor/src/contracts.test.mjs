// Copyright (c) 2026, afmcoltd
import { describe, expect, it } from "vitest";

import { messages } from "./i18n.js";
import {
  matchesDriverFilter,
  normalizeDriverFilter,
  uniqueDriverOptions,
} from "./mapFilters.js";
import { createMapFitPolicy } from "./mapFitPolicy.js";
import { isActivePlan, isHistoryPlan, isPendingPlan, laneForPlan } from "./planLanes.js";

function leafKeys(value, prefix = "") {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return child && typeof child === "object" ? leafKeys(child, path) : [path];
  });
}

describe("route supervisor presentation contracts", () => {
  it("keeps approved work active until its trip reaches a terminal state", () => {
    expect(isActivePlan({ approval: "Approved", trip: { status: "Planned" } })).toBe(true);
    expect(isActivePlan({ approval: "Approved", trip: { status: "Dispatched" } })).toBe(true);
    expect(isActivePlan({ approval: "Approved" })).toBe(true);
    expect(isActivePlan({ approval: "Approved", trip: { status: "Completed" } })).toBe(false);
  });

  it("records rejected, completed, and cancelled plans in history", () => {
    expect(isHistoryPlan({ approval: "Rejected" })).toBe(true);
    expect(isHistoryPlan({ approval: "Approved", trip: { status: "Completed" } })).toBe(true);
    expect(isHistoryPlan({ approval: "Approved", trip: { status: "Cancelled" } })).toBe(true);
    expect(isHistoryPlan({ approval: "Pending" })).toBe(false);
  });

  it("keeps a pending plan in exactly one lane even when a trip is terminal", () => {
    const plan = { approval: "Pending", trip: { status: "Completed" } };
    expect(laneForPlan(plan)).toBe("pending");
    expect(isPendingPlan(plan)).toBe(true);
    expect(isHistoryPlan(plan)).toBe(false);
    expect(isActivePlan(plan)).toBe(false);
  });

  it("ships the same translation contract in Arabic and English", () => {
    expect(leafKeys(messages.ar).sort()).toEqual(leafKeys(messages.en).sort());
  });

  it("uses stable driver ids while accepting legacy display-name filters", () => {
    const rows = [
      { driver: "DRV-002", driver_name: "Saleh" },
      { driver: "DRV-001", driver_name: "Ahmed" },
    ];
    expect(uniqueDriverOptions(rows)).toEqual([
      { label: "Ahmed", value: "DRV-001" },
      { label: "Saleh", value: "DRV-002" },
    ]);
    expect(matchesDriverFilter(rows[0], "DRV-002")).toBe(true);
    expect(matchesDriverFilter(rows[0], "Saleh")).toBe(true);
    expect(normalizeDriverFilter(rows, "Saleh")).toBe("DRV-002");
  });

  it("fits once, then waits for an explicit filter change", () => {
    const policy = createMapFitPolicy();
    expect(policy.pending).toBe(true);
    policy.resolve(false);
    expect(policy.pending).toBe(true);
    policy.resolve(true);
    expect(policy.pending).toBe(false);
    policy.request();
    expect(policy.pending).toBe(true);
  });
});
