import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

import { createDriverGateway } from "./gateway.js";
import { driverRoutes } from "./routes.js";
import DriverPage from "./DriverPage.vue";

vi.mock("frappe-ui", () => ({
  Badge: { template: "<span />" },
  Button: { template: "<button><slot /></button>" },
  FeatherIcon: { template: "<i />" },
}));

describe("Masar driver feature", () => {
  it("keeps personal service and bus execution while excluding fleet self-service", () => {
    expect(driverRoutes.map((route) => route.path)).toEqual([
      "/today",
      "/route",
      "/trips",
      "/requests",
      "/profile",
      "/accommodation",
      "/custody",
      "/route/:trip",
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

  it("renders an empty state for an object containing an empty collection", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: "/today",
        component: DriverPage,
        meta: { view: { gateway: "today", collections: ["items"], empty: "لا توجد رحلات." } },
      }],
    });
    await router.push("/today");
    await router.isReady();
    const wrapper = mount(DriverPage, {
      global: {
        plugins: [router],
        provide: { driverGateway: { today: vi.fn().mockResolvedValue({ items: [] }) } },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("لا توجد رحلات.");
    expect(wrapper.find(".feature-details").exists()).toBe(false);
  });
});
