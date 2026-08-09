// Copyright (c) 2026, afmcoltd
import { beforeEach, describe, expect, it, vi } from "vitest";

const call = vi.fn();
vi.mock("@shared/call", () => ({ call }));

const {
  getActiveDriverPositions,
  getSupervisorPlan,
} = await import("./api.js");

describe("route supervisor API pagination contracts", () => {
  beforeEach(() => call.mockReset());

  it("requests one owned plan for a deep link", async () => {
    call.mockResolvedValue({ plan: { name: "RP-0099" } });

    await getSupervisorPlan("RP-0099");

    expect(call).toHaveBeenCalledWith(
      "apex.salis.api.route_supervisor.get_supervisor_plan",
      { args: { name: "RP-0099" } },
    );
  });

  it("passes the page cursor to the fleet positions endpoint", async () => {
    call.mockResolvedValue({ positions: [], start: 50, page_length: 25 });

    await getActiveDriverPositions(50, 25);

    expect(call).toHaveBeenCalledWith(
      "apex.salis.api.route_supervisor.get_active_driver_positions",
      { args: { start: 50, page_length: 25 } },
    );
  });
});
