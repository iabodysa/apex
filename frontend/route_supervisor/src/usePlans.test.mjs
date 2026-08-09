// Copyright (c) 2026, afmcoltd
import { beforeEach, describe, expect, it, vi } from "vitest";

const getSupervisorContext = vi.fn();
const getSupervisorPlan = vi.fn();
const getSupervisorPlans = vi.fn();
const approveRoutePlan = vi.fn();
const rejectRoutePlan = vi.fn();

vi.mock("vue", async () => {
  const vue = await vi.importActual("vue");
  return { ...vue, provide: vi.fn() };
});

vi.mock("./api.js", () => ({
  approveRoutePlan,
  getSupervisorContext,
  getSupervisorPlan,
  getSupervisorPlans,
  rejectRoutePlan,
}));

const { createPlansStore } = await import("./usePlans.js");

describe("route supervisor plan store", () => {
  beforeEach(() => {
    getSupervisorContext.mockReset();
    getSupervisorPlan.mockReset();
    getSupervisorPlans.mockReset();
    approveRoutePlan.mockReset();
    rejectRoutePlan.mockReset();
  });

  it("exposes full active and history counts instead of loaded-page lengths", async () => {
    getSupervisorContext.mockResolvedValue({
      plans: [{ name: "RP-1", approval: "Approved" }],
      counts: { pending: 7, decided: 58, active: 41, history: 17 },
      pages: {
        pending: { has_more: false },
        decided: { has_more: true },
      },
    });
    const store = createPlansStore();

    await store.load();

    expect(store.activePlans.value).toHaveLength(1);
    expect(store.activeCount.value).toBe(41);
    expect(store.historyCount.value).toBe(17);
  });

  it("loads a plan named by a deep link when it is outside the first pages", async () => {
    getSupervisorContext.mockResolvedValue({
      plans: [{ name: "RP-1", approval: "Pending" }],
      counts: { pending: 51, decided: 0, active: 0, history: 0 },
      pages: { pending: { has_more: true }, decided: { has_more: false } },
    });
    getSupervisorPlan.mockResolvedValue({
      plan: { name: "RP-0099", approval: "Pending", trip: null },
    });
    const store = createPlansStore();
    await store.load();

    const result = await store.ensurePlan("RP-0099");

    expect(result).toEqual({ ok: true, plan: expect.objectContaining({ name: "RP-0099" }) });
    expect(getSupervisorPlan).toHaveBeenCalledWith("RP-0099");
    expect(store.planByName("RP-0099")).toEqual(
      expect.objectContaining({ name: "RP-0099" }),
    );
    expect(store.targetLoadState.value).toBe("ready");
  });

  it("does not count a targeted deep-link plan in the server page cursor", async () => {
    const firstPage = Array.from({ length: 50 }, (_, index) => ({
      name: `RP-${String(index + 1).padStart(4, "0")}`,
      approval: "Pending",
    }));
    getSupervisorContext.mockResolvedValue({
      plans: firstPage,
      counts: { pending: 61, decided: 0, active: 0, history: 0 },
      pages: { pending: { has_more: true }, decided: { has_more: false } },
    });
    getSupervisorPlan.mockResolvedValue({
      plan: { name: "RP-0099", approval: "Pending", trip: null },
    });
    getSupervisorPlans.mockResolvedValue({ plans: [], has_more: false });
    const store = createPlansStore();
    await store.load();
    await store.ensurePlan("RP-0099");

    await store.loadMore("pending");

    expect(getSupervisorPlans).toHaveBeenCalledWith("pending", 50);
  });

  it("keeps a selected first-page plan available after a decision moves its lane", async () => {
    getSupervisorContext
      .mockResolvedValueOnce({
        plans: [{ name: "RP-1", approval: "Pending" }],
        counts: { pending: 1, decided: 0, active: 0, history: 0 },
        pages: { pending: { has_more: false }, decided: { has_more: false } },
      })
      .mockResolvedValueOnce({
        plans: [],
        counts: { pending: 0, decided: 1, active: 1, history: 0 },
        pages: { pending: { has_more: false }, decided: { has_more: true } },
      });
    approveRoutePlan.mockResolvedValue({ ok: true });
    getSupervisorPlan.mockResolvedValue({
      plan: { name: "RP-1", approval: "Approved", trip: { status: "Planned" } },
    });
    const store = createPlansStore();
    await store.load();

    const result = await store.approve("RP-1");

    expect(result).toEqual({ ok: true });
    expect(getSupervisorPlan).toHaveBeenCalledWith("RP-1");
    expect(store.planByName("RP-1")).toEqual(
      expect.objectContaining({ approval: "Approved" }),
    );
  });
});
