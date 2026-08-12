import { describe, expect, it, vi } from "vitest";

import { createDriverGateway } from "./gateway.js";
import { driverRoutes } from "./routes.js";

describe("Masar driver feature", () => {
  it("keeps personal service and bus execution while excluding fleet self-service", () => {
    expect(driverRoutes.map((route) => route.path)).toEqual([
      "/today",
      "/profile",
      "/accommodation",
      "/custody",
      "/requests",
      "/route",
      "/route/:trip",
      "/trips",
    ]);
    const source = JSON.stringify(driverRoutes);
    expect(source).not.toMatch(/fuel|quota|clearance|vehicle-custody|fleet-complaint/i);
  });

  it("sends only the trip id to idempotent execution endpoints", async () => {
    const call = vi.fn().mockResolvedValue({ message: { state: "Started" } });
    const gateway = createDriverGateway(call);

    await gateway.startTrip("TRIP-001");
    expect(call).toHaveBeenCalledWith(
      "apex.salis.api.driver_portal.start_my_trip",
      { dispatch_trip: "TRIP-001" },
    );
    expect(Object.keys(call.mock.calls[0][1])).toEqual(["dispatch_trip"]);
  });

  it("loads a Masar-only today model rather than fleet home data", async () => {
    const call = vi.fn().mockResolvedValue({ message: { trips: [] } });
    await createDriverGateway(call).today();
    expect(call).toHaveBeenCalledWith(
      "apex.salis.api.driver_portal.personal.get_masar_today",
    );
  });
});
