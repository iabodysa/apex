import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const { resources } = vi.hoisted(() => ({ resources: new Map() }));

vi.mock("frappe-ui", () => ({
  Badge: { template: "<span />" },
  Button: { template: "<button><slot /></button>" },
  createResource: vi.fn(({ url }) => resources.get(url) || {
    data: null,
    loading: false,
    error: null,
    fetch: vi.fn().mockResolvedValue(null),
  }),
}));

import CurrentVehiclePage from "./pages/CurrentVehiclePage.vue";
import FuelQuotaPage from "./pages/FuelQuotaPage.vue";

const responseError = {
  message: 'Traceback: File "/home/frappe/apps/apex/private.py", line 4',
  response: {
    status: 403,
    data: {
      _server_messages: JSON.stringify([
        JSON.stringify({ message: "لا تملك صلاحية عرض هذه البيانات." }),
      ]),
    },
  },
};

describe("fleet self-service error surfaces", () => {
  beforeEach(() => resources.clear());

  it.each([
    [CurrentVehiclePage, "apex.salis.api.fleet_employee.get_my_vehicle"],
    [FuelQuotaPage, "apex.salis.api.fleet_employee.get_my_fuel_quota"],
  ])("passes the real frappe-ui response error through the shared safe state", async (component, url) => {
    resources.set(url, {
      data: null,
      loading: false,
      error: responseError,
      fetch: vi.fn().mockResolvedValue(null),
    });
    const wrapper = mount(component, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    });
    await flushPromises();

    expect(wrapper.get("[role='alert']").text()).toContain("لا تملك صلاحية عرض هذه البيانات.");
    expect(wrapper.get("[role='alert']").text()).not.toContain("Traceback");
    expect(wrapper.find("[role='alert'] button").exists()).toBe(false);
    wrapper.unmount();
  });
});
