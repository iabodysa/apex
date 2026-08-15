import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

import { createDriverGateway } from "./gateway.js";
import { driverRoutes } from "./routes.js";
import DriverPage from "./DriverPage.vue";
import DriverTripPage from "./DriverTripPage.vue";

const { resourceData, resourceCalls } = vi.hoisted(() => ({
  resourceData: new Map(),
  resourceCalls: [],
}));

vi.mock("frappe-ui", () => ({
  Badge: { props: ["label"], template: "<span>{{ label }}</span>" },
  Button: {
    props: ["disabled"],
    template: "<button :disabled='disabled'><slot /></button>",
  },
  ErrorMessage: { props: ["message"], template: "<p>{{ message }}</p>" },
  FormControl: { template: "<input />" },
  LoadingIndicator: { template: "<span />" },
  createResource: vi.fn((options) => {
    let url = options.url;
    return {
      update(next) {
        if (next.url) url = next.url;
      },
      fetch: vi.fn(async (params) => {
        resourceCalls.push([url, params]);
        const value = resourceData.get(url);
        if (value instanceof Error) throw value;
        return typeof value === "function" ? value(params) : value;
      }),
    };
  }),
  toast: { create: vi.fn() },
}));

// The shape frappe-ui's frappeRequest actually throws: HTTP status only on response.
function frappeError(url, status, messages) {
  const error = new Error(`/api/method/${url} ValidationError`);
  error.response = { status };
  error.messages = messages;
  return error;
}

describe("Masar driver feature", () => {
  beforeEach(() => {
    resourceData.clear();
    resourceCalls.length = 0;
  });

  it("reads the driver denial from response.status and drops the retry", async () => {
    const url = "apex.salis.api.driver_portal.personal.get_masar_today";
    resourceData.set(url, frappeError(url, 403, ["حسابك غير مرتبط بسائق."]));
    const router = createRouter({ history: createMemoryHistory(), routes: driverRoutes });
    await router.push("/today");
    await router.isReady();
    const wrapper = mount(DriverPage, { global: { plugins: [router] } });
    await flushPromises();

    const alert = wrapper.get("[role='alert']");
    expect(alert.get("h2").text()).toBe("تعذّر فتح القسم");
    expect(alert.text()).toContain("حسابك غير مرتبط بسائق.");
    expect(alert.text()).not.toContain("/api/method/");
    expect(alert.find("button").exists()).toBe(false);
    wrapper.unmount();
  });

  it("keeps the trip server message and its retry for a retryable failure", async () => {
    const url = "apex.salis.api.driver_portal.my_trip_route";
    resourceData.set(url, frappeError(url, 500, ["تعذّر الوصول إلى الخادم."]));
    const router = createRouter({ history: createMemoryHistory(), routes: driverRoutes });
    await router.push("/route/TRIP-1");
    await router.isReady();
    const wrapper = mount(DriverTripPage, {
      global: { plugins: [router], provide: { portalSubscribe: () => () => {}, driverGateway: {} } },
    });
    await flushPromises();

    const alert = wrapper.get("[role='alert']");
    expect(alert.get("h2").text()).toBe("تعذّر تحميل الرحلة");
    expect(alert.text()).toContain("تعذّر الوصول إلى الخادم.");
    expect(alert.text()).not.toContain("/api/method/");
    expect(alert.find("button").exists()).toBe(true);
    wrapper.unmount();
  });

  it("links a route card by the id its own endpoint emits", async () => {
    // my_worker_route_today names the id after the DocType it came from, my_trips_recent
    // returns name; a card built on one key alone links the other tab to /route/undefined.
    for (const [path, url, row] of [
      ["/route", "apex.salis.api.driver_portal.my_worker_route_today", { dispatch_trip: "DT-1", route_name: "خط الشمال" }],
      ["/trips", "apex.salis.api.driver_portal.my_trips_recent", { name: "DT-2", route_name: "خط الجنوب" }],
    ]) {
      resourceData.set(url, { trips: [row] });
      const router = createRouter({ history: createMemoryHistory(), routes: driverRoutes });
      await router.push(path);
      await router.isReady();
      const wrapper = mount(DriverPage, { global: { plugins: [router] } });
      await flushPromises();

      expect(wrapper.get("a.record-card").attributes("href")).toBe(`/route/${row.dispatch_trip || row.name}`);
      wrapper.unmount();
    }
  });

  it("keeps personal service and bus execution while excluding fleet self-service", () => {
    expect(driverRoutes.map((route) => route.path)).toEqual(["/today", "/route", "/trips", "/requests", "/profile", "/accommodation", "/custody", "/route/:trip"]);
    const source = JSON.stringify(driverRoutes);
    expect(source).not.toMatch(/fuel|quota|clearance|vehicle-custody|fleet-complaint/i);
  });

  it("sends only the trip id to idempotent execution endpoints", async () => {
    const call = vi.fn().mockResolvedValue({ message: { state: "Started" } });
    const gateway = createDriverGateway(call);

    await gateway.startTrip("TRIP-001");
    expect(call).toHaveBeenCalledWith("apex.salis.api.driver_portal.start_my_trip", { dispatch_trip: "TRIP-001" });
    expect(Object.keys(call.mock.calls[0][1])).toEqual(["dispatch_trip"]);
  });

  it("loads a page-local Masar-only today resource", async () => {
    resourceData.set("apex.salis.api.driver_portal.personal.get_masar_today", {
      trips: [],
    });
    const router = createRouter({
      history: createMemoryHistory(),
      routes: driverRoutes,
    });
    await router.push("/today");
    await router.isReady();
    const wrapper = mount(DriverPage, { global: { plugins: [router] } });
    await flushPromises();

    expect(resourceCalls).toContainEqual(["apex.salis.api.driver_portal.personal.get_masar_today", undefined]);
    wrapper.unmount();
  });

  it("shows the shared record skeleton while a driver read is pending", async () => {
    resourceData.set("apex.salis.api.driver_portal.personal.get_masar_today", () => new Promise(() => {}));
    const router = createRouter({ history: createMemoryHistory(), routes: driverRoutes });
    await router.push("/today");
    await router.isReady();
    const wrapper = mount(DriverPage, { global: { plugins: [router] } });

    expect(wrapper.find(".portal-skeleton").exists()).toBe(true);
    expect(wrapper.find(".feature-page__empty").exists()).toBe(false);
    wrapper.unmount();
  });

  it("keeps boarding, arrival, and exception handling on the trip screen", async () => {
    const tripRoute = driverRoutes.find((route) => route.path === "/route/:trip");
    expect(tripRoute.component).toBe(DriverTripPage);

    const call = vi.fn().mockResolvedValue({ message: {} });
    const gateway = createDriverGateway(call);
    await gateway.arriveAtStop("DT-1", "STOP-1");
    await gateway.notifyPassengers("DT-1");
    await gateway.markNotBoarded("DT-1", "EMP-1");
    await gateway.depart("DT-1");

    expect(call.mock.calls).toEqual([
      ["apex.salis.api.driver_portal.mark_arrived", { dispatch_trip: "DT-1", route_stop: "STOP-1" }],
      ["apex.salis.api.boarding_flow.notify_remaining_passengers", { dispatch_trip: "DT-1" }],
      ["apex.salis.api.boarding_flow.driver_mark_not_boarded", { dispatch_trip: "DT-1", employee: "EMP-1" }],
      ["apex.salis.api.boarding_flow.depart_and_finalize", { dispatch_trip: "DT-1" }],
    ]);
  });

  it("lets the driver undo a completed stop through the canonical endpoint", async () => {
    const call = vi.fn().mockResolvedValue({ message: {} });
    const gateway = createDriverGateway(call);

    await gateway.setStopProgress("DT-1", "STOP-1", false);

    expect(call).toHaveBeenCalledWith("apex.salis.api.driver_portal.mark_stop_progress", { dispatch_trip: "DT-1", route_stop: "STOP-1", done: 0 });
  });

  it("shows stop details, passenger calls, and active wait requests", async () => {
    resourceData.set("apex.salis.api.driver_portal.my_trip_route", {
      route_name: "خط السكن",
      status: "Dispatched",
      started: true,
      stops: [
        {
          route_stop: "STOP-1",
          stop_name: "بوابة السكن",
          planned_time: "06:30:00",
          pickup: {
            building_name: "سكن العرض",
            city: "الرياض",
            google_maps_url: "https://maps.example/stop",
          },
        },
      ],
      workers: [
        {
          employee: "EMP-1",
          employee_name: "عامل العرض",
          pickup_point: "البوابة",
          phone: "0500000000",
        },
      ],
    });
    resourceData.set("apex.salis.api.boarding_flow.get_trip_boarding", {
      worker_wait_request_max: 3,
      worker_wait_request_seconds: 120,
      grace_elapsed: false,
      workers: [{ employee: "EMP-1", status: "Pending", wait_count: 1 }],
    });
    resourceData.set("apex.salis.api.driver_portal.personal.get_masar_today", {
      realtime_room: "",
    });
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/route/:trip", component: DriverTripPage }],
    });
    await router.push("/route/DT-1");
    await router.isReady();
    const wrapper = mount(DriverTripPage, {
      global: {
        plugins: [router],
        provide: {
          portalSubscribe: () => () => {},
          driverGateway: {},
        },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("6:30 ص");
    expect(wrapper.text()).toContain("سكن العرض");
    expect(wrapper.text()).toContain("الرياض");
    expect(wrapper.text()).toContain("طلب الانتظار 1 من 3");
    expect(wrapper.get('a[href="tel:0500000000"]').text()).toContain("اتصل بالعامل");
    wrapper.unmount();
  });

  it("subscribes to the trip room once, not again on every poll", async () => {
    resourceData.set("apex.salis.api.driver_portal.my_trip_route", { name: "DT-1", stops: [], workers: [] });
    resourceData.set("apex.salis.api.boarding_flow.get_trip_boarding", { workers: [] });
    resourceData.set("apex.salis.api.driver_portal.personal.get_masar_today", { realtime_room: "trip:DT-1" });
    const subscribe = vi.fn(() => () => {});
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/route/:trip", component: DriverTripPage }],
    });
    await router.push("/route/DT-1");
    await router.isReady();
    vi.useFakeTimers();
    const wrapper = mount(DriverTripPage, {
      global: { plugins: [router], provide: { portalSubscribe: subscribe, driverGateway: {} } },
    });
    await flushPromises();
    const afterFirstLoad = subscribe.mock.calls.length;

    await vi.advanceTimersByTimeAsync(30000);
    await flushPromises();

    expect(afterFirstLoad).toBeGreaterThan(0);
    expect(subscribe).toHaveBeenCalledTimes(afterFirstLoad);
    wrapper.unmount();
    vi.useRealTimers();
  });

  it("renders an empty state for an object containing an empty collection", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: "/today",
          component: DriverPage,
          meta: {
            view: {
              endpoint: "apex.test.driver.today",
              collections: ["items"],
              empty: "لا توجد رحلات.",
            },
          },
        },
      ],
    });
    resourceData.set("apex.test.driver.today", { items: [] });
    await router.push("/today");
    await router.isReady();
    const wrapper = mount(DriverPage, {
      global: {
        plugins: [router],
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("لا توجد رحلات.");
    expect(wrapper.find(".feature-details").exists()).toBe(false);
  });
});
