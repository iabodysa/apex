import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const { calls, dataByUrl } = vi.hoisted(() => ({
  calls: [],
  dataByUrl: new Map(),
}));

vi.mock("frappe-ui", () => ({
  ErrorMessage: { props: ["message"], template: "<p>{{ message }}</p>" },
  LoadingIndicator: { template: "<span />" },
  Button: { template: "<button><slot /></button>" },
  createResource: vi.fn(({ url }) => ({
    data: dataByUrl.get(url) ?? null,
    loading: false,
    error: null,
    fetch: vi.fn(async (params) => {
      calls.push([url, params]);
      return dataByUrl.get(url) ?? null;
    }),
  })),
}));

import { building, selectBuilding } from "./building.js";
import TodayPage from "./pages/TodayPage.vue";

const endpoints = Object.freeze({
  buildings: "apex.habitat.api.front_desk.list_supervisor_buildings",
  beds: "apex.habitat.api.front_desk.get_building_grid",
  maintenance: "apex.habitat.api.front_desk.building_open_requests",
  arrivals: "apex.habitat.api.arrivals_desk.get_expected_arrivals",
  safety: "apex.habitat.api.safety_checklist.get_due_cadences",
});

async function mountToday(capabilities) {
  globalThis.window.apex_portal = { capabilities };
  selectBuilding("BLD-1");
  const wrapper = mount(TodayPage, {
    global: {
      stubs: {
        BuildingPicker: { template: "<div data-building-picker />" },
        RouterLink: {
          props: ["to"],
          template: '<a :data-to="to"><slot /></a>',
        },
      },
    },
  });
  await flushPromises();
  return wrapper;
}

describe("housing Today capability boundaries", () => {
  beforeEach(() => {
    calls.length = 0;
    dataByUrl.clear();
    dataByUrl.set(endpoints.buildings, []);
    dataByUrl.set(endpoints.beds, { summary: { available: 3 } });
    dataByUrl.set(endpoints.maintenance, { open_requests: 2 });
    dataByUrl.set(endpoints.arrivals, { pending: 1 });
    dataByUrl.set(endpoints.safety, { due: [], awaiting: [] });
  });

  afterEach(() => {
    selectBuilding("");
    delete globalThis.window.apex_portal;
  });

  it("calls and links only arrivals when check-in is the sole housing-domain capability", async () => {
    const wrapper = await mountToday(["today", "check_in"]);
    const urls = calls.map(([url]) => url);

    expect(urls).toContain(endpoints.arrivals);
    expect(urls).not.toContain(endpoints.beds);
    expect(urls).not.toContain(endpoints.maintenance);
    expect(urls).not.toContain(endpoints.safety);
    expect(urls).not.toContain(endpoints.buildings);
    expect(wrapper.find('[data-to="/arrivals"]').exists()).toBe(true);
    for (const unauthorized of ["/beds", "/maintenance", "/maintenance/new", "/custody", "/rounds"]) {
      expect(wrapper.find(`[data-to="${unauthorized}"]`).exists(), unauthorized).toBe(false);
    }
    wrapper.unmount();
  });

  it("uses each exact capability for bed, maintenance, custody, creation, and safety domains", async () => {
    const wrapper = await mountToday([
      "today",
      "estate_read",
      "maintenance_read",
      "maintenance_create",
      "custody_read",
      "safety_read",
    ]);
    const urls = calls.map(([url]) => url);

    expect(urls).toEqual(expect.arrayContaining([
      endpoints.buildings,
      endpoints.beds,
      endpoints.maintenance,
      endpoints.safety,
    ]));
    expect(urls).not.toContain(endpoints.arrivals);
    for (const allowed of ["/beds", "/maintenance", "/maintenance/new", "/custody", "/rounds"]) {
      expect(wrapper.find(`[data-to="${allowed}"]`).exists(), allowed).toBe(true);
    }
    expect(wrapper.find('[data-to="/arrivals"]').exists()).toBe(false);
    wrapper.unmount();
  });
});
