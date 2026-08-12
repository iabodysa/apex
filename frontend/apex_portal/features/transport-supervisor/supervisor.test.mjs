import { describe, expect, it, vi } from "vitest";

import { createTransportSupervisorGateway } from "./gateway.js";
import { supervisorRedirects, supervisorRoutes } from "./routes.js";

describe("Masar transport supervisor feature", () => {
  it("centres operations on requests, shifts, plans and dispatch trips", () => {
    expect(supervisorRoutes.map((route) => route.path)).toEqual([
      "/requests",
      "/shifts",
      "/plans",
      "/plans/new",
      "/plans/:name",
      "/trips",
      "/trips/:name",
      "/map",
      "/history",
    ]);
  });

  it("preserves the legacy hash redirects", () => {
    expect(supervisorRedirects).toEqual([
      { path: "/approvals", redirect: "/requests" },
      { path: "/routes", redirect: "/plans" },
      { path: "/plan/:name/:tab?", redirect: expect.any(Function) },
    ]);
    expect(supervisorRedirects[2].redirect({ params: { name: "RP-1" } })).toBe("/plans/RP-1");
  });

  it("uses workflow actions instead of parallel supervisor approval fields", async () => {
    const call = vi.fn().mockResolvedValue({ message: { status: "Validated" } });
    const gateway = createTransportSupervisorGateway(call);
    await gateway.applyRequestAction("TR-1", "Validate");
    expect(call).toHaveBeenCalledWith(
      "apex.salis.api.route_supervisor.apply_transport_request_action",
      { name: "TR-1", action: "Validate" },
    );
  });
});
