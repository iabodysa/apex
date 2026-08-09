// Copyright (c) 2026, afmcoltd
import { describe, expect, it } from "vitest";

import {
  countRoundMarks,
  draftCount,
  occupancyMetrics,
  pendingArrivals,
  todayPageState,
} from "../today.js";

describe("housing today summary", () => {
  it("uses server-owned bed totals without recomputing bed state", () => {
    expect(
      occupancyMetrics({ total_beds: 12, occupied: 8, available: 2, blocked: 1, out_of_service: 1 }),
    ).toEqual({ total: 12, occupied: 8, available: 2, unavailable: 2 });
  });

  it("counts pending arrivals and local work safely", () => {
    expect(pendingArrivals({ total: 7, arrived: 3 })).toBe(4);
    expect(pendingArrivals({ pending: 2, total: 9, arrived: 1 })).toBe(2);
    expect(draftCount({ A: {}, B: {} })).toBe(2);
    expect(draftCount(null)).toBe(0);
    expect(
      countRoundMarks({ Daily: { door: { verdict: "pass" }, alarm: { verdict: "" } } }),
    ).toBe(1);
  });

  it("never presents a complete API outage as a ready overview", () => {
    expect(todayPageState({ loading: true, loaded: 0, failed: 0, total: 4 })).toBe("loading");
    expect(todayPageState({ loading: false, loaded: 0, failed: 4, total: 4 })).toBe("error");
    expect(todayPageState({ loading: false, loaded: 2, failed: 2, total: 4 })).toBe("ready");
  });
});
