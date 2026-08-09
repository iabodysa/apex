// Copyright (c) 2026, afmcoltd
import { describe, expect, it } from "vitest";

import { loadedForLane, mergePlanPage, pagedSubsetState } from "./planPages.js";

describe("route supervisor plan pages", () => {
  it("counts each server lane independently", () => {
    const plans = [
      { name: "P-1", approval: "Pending" },
      { name: "P-2", approval: "Approved" },
      { name: "P-3", approval: "Rejected" },
    ];

    expect(loadedForLane(plans, "pending")).toBe(1);
    expect(loadedForLane(plans, "decided")).toBe(2);
  });

  it("appends in server order and replaces duplicates without moving them", () => {
    const existing = [
      { name: "P-1", approval: "Pending", modified: "old" },
      { name: "P-2", approval: "Approved" },
    ];
    const incoming = [
      { name: "P-1", approval: "Pending", modified: "new" },
      { name: "P-3", approval: "Pending" },
    ];

    expect(mergePlanPage(existing, incoming)).toEqual([
      { name: "P-1", approval: "Pending", modified: "new" },
      { name: "P-2", approval: "Approved" },
      { name: "P-3", approval: "Pending" },
    ]);
  });

  it("keeps an empty decided subset open while later pages may contain it", () => {
    expect(pagedSubsetState({ loadState: "ready", itemCount: 0, hasMore: true })).toBe("ready");
    expect(pagedSubsetState({ loadState: "ready", itemCount: 0, hasMore: false })).toBe("empty");
  });
});
