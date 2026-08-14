import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { createResource } from "frappe-ui";
import FuelApprovalQueuePage from "./pages/FuelApprovalQueuePage.vue";
import VehicleWorkspacePage from "./pages/VehicleWorkspacePage.vue";
import SupervisorOverviewPage from "./pages/SupervisorOverviewPage.vue";
import QueuePage from "./components/QueuePage.vue";

const { resources } = vi.hoisted(() => ({ resources: new Map() }));

vi.mock("frappe-ui", () => ({
  Badge: { template: "<span />" },
  Button: { props: ["label"], template: "<button><slot />{{ label }}</button>" },
  Dialog: { template: "<div><slot name='body-content' /></div>" },
  FormControl: { template: "<textarea />" },
  createResource: vi.fn(
    ({ url }) =>
      resources.get(url) || {
        data: null,
        loading: false,
        error: null,
        fetch: vi.fn().mockResolvedValue(null),
        submit: vi.fn().mockResolvedValue(null),
      },
  ),
}));

function readResource(overrides = {}) {
  return {
    data: null,
    loading: false,
    error: null,
    fetch: vi.fn().mockResolvedValue(null),
    ...overrides,
  };
}

async function mountVehicle() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/vehicles/:vehicle", component: VehicleWorkspacePage }],
  });
  await router.push("/vehicles/VEH-1");
  await router.isReady();
  const wrapper = mount(VehicleWorkspacePage, {
    global: { plugins: [router] },
  });
  await flushPromises();
  return wrapper;
}

describe("fleet operations async states", () => {
  beforeEach(() => {
    resources.clear();
    vi.clearAllMocks();
  });

  it("creates only the resources owned by the fuel approval page", () => {
    mount(FuelApprovalQueuePage);

    expect(createResource).toHaveBeenCalledTimes(3);
    expect(createResource.mock.calls.map(([options]) => options.url)).toEqual(["apex.salis.api.fuel_console.get_pending_fuel_requests", "apex.salis.api.fuel_console.approve_fuel_request", "apex.salis.api.fuel_console.reject_fuel_request"]);
  });

  it("shows the fuel queue error before the empty state and offers retry", async () => {
    const fuel = readResource({ data: [], error: new Error("network") });
    resources.set("apex.salis.api.fuel_console.get_pending_fuel_requests", fuel);
    const wrapper = mount(FuelApprovalQueuePage);
    await flushPromises();

    expect(wrapper.text()).toContain("تعذّر تحميل طلبات الوقود");
    expect(wrapper.text()).not.toContain("لا توجد طلبات بانتظار الاعتماد");
    await wrapper.get("[role='alert'] button").trigger("click");
    expect(fuel.fetch).toHaveBeenCalled();
  });

  it("shows a vehicle request error instead of reporting the vehicle missing", async () => {
    resources.set("apex.salis.api.fleet_os.get_fleet_os", readResource({ error: new Error("network") }));
    resources.set("apex.salis.api.fleet_os.get_vehicle_timeline", readResource());
    const wrapper = await mountVehicle();

    expect(wrapper.text()).toContain("تعذّر تحميل المركبة");
    expect(wrapper.text()).not.toContain("المركبة غير موجودة");
  });

  it("keeps the workspace visible while timeline loading or error is reported", async () => {
    const vehicleData = {
      vehicles: [{ name: "VEH-1", plate: "1234", capabilities: {} }],
    };
    resources.set("apex.salis.api.fleet_os.get_fleet_os", readResource({ data: vehicleData }));
    resources.set("apex.salis.api.fleet_os.get_vehicle_timeline", readResource({ loading: true }));
    const loading = await mountVehicle();
    expect(loading.text()).toContain("جاري تحميل السجل الزمني");
    loading.unmount();

    const timeline = readResource({ error: new Error("network") });
    resources.set("apex.salis.api.fleet_os.get_vehicle_timeline", timeline);
    const failed = await mountVehicle();
    expect(failed.text()).toContain("تعذّر تحميل السجل الزمني");
    await failed.get("[role='alert'] button").trigger("click");
    expect(timeline.fetch).toHaveBeenCalledWith({ plate: "VEH-1" });
  });

  it("shows actionable normalized queue detail without leaking a server traceback", async () => {
    const queue = readResource({
      error: {
        message: 'Traceback: File "/home/frappe/apps/apex/secret.py", line 9',
        _server_messages: JSON.stringify([
          JSON.stringify({ message: "لا تملك صلاحية اعتماد هذا الطلب." }),
        ]),
      },
    });
    const wrapper = mount(QueuePage, {
      props: {
        title: "قائمة التسليم",
        resource: queue,
        empty: "لا توجد سجلات.",
      },
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("لا تملك صلاحية اعتماد هذا الطلب.");
    expect(wrapper.text()).not.toContain("Traceback");
    expect(wrapper.text()).not.toContain("/home/frappe");
  });

  it.each([
    ["fuel approvals", FuelApprovalQueuePage, "apex.salis.api.fuel_console.get_pending_fuel_requests"],
    ["vehicle workspace", VehicleWorkspacePage, "apex.salis.api.fleet_os.get_fleet_os"],
    ["supervisor overview", SupervisorOverviewPage, "apex.salis.api.fleet_os.get_operations_overview"],
  ])("renders safe frappe-ui response errors on %s", async (_name, component, url) => {
    const error = {
      message: 'Traceback: File "/home/frappe/apps/apex/secret.py", line 9',
      response: {
        status: 403,
        data: {
          _server_messages: JSON.stringify([
            JSON.stringify({ message: "لا تملك صلاحية عرض هذه البيانات." }),
          ]),
        },
      },
    };
    resources.set(url, readResource({ error }));
    if (component === VehicleWorkspacePage) {
      resources.set("apex.salis.api.fleet_os.get_vehicle_timeline", readResource());
    }
    const wrapper = component === VehicleWorkspacePage
      ? await mountVehicle()
      : mount(component, { global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } } });
    await flushPromises();

    expect(wrapper.get("[role='alert']").text()).toContain("لا تملك صلاحية عرض هذه البيانات.");
    expect(wrapper.get("[role='alert']").text()).not.toContain("Traceback");
    expect(wrapper.find("[role='alert'] button").exists()).toBe(false);
    wrapper.unmount();
  });
});
