import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const { calls, dataByUrl } = vi.hoisted(() => ({
  calls: [],
  dataByUrl: new Map(),
}));

vi.mock("frappe-ui", () => ({
  ErrorMessage: { props: ["message"], template: "<p>{{ message }}</p>" },
  LoadingIndicator: { template: "<span />" },
  Button: { props: ["label"], template: "<button>{{ label }}<slot /></button>" },
  Select: { props: ["options"], template: '<select data-building-select />' },
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

async function mountToday(capabilities, initialBuilding = "BLD-1") {
  globalThis.window.apex_portal = { capabilities };
  selectBuilding(initialBuilding);
  const wrapper = mount(TodayPage, {
    global: {
      stubs: {
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
    dataByUrl.set(endpoints.buildings, [
      { building: "BLD-1", building_title: "سكن الشمال", occupied: 4, available: 2, blocked: 0, oos: 0, occupancy_pct: 66 },
    ]);
    dataByUrl.set(endpoints.beds, { summary: { available: 3 } });
    dataByUrl.set(endpoints.maintenance, { open_requests: 2 });
    dataByUrl.set(endpoints.arrivals, { pending: 1 });
    dataByUrl.set(endpoints.safety, { due: [], awaiting: [] });
  });

  afterEach(() => {
    selectBuilding("");
    delete globalThis.window.apex_portal;
  });

  it("selects a scoped building and loads only arrivals for a check-in user", async () => {
    const wrapper = await mountToday(["today", "check_in"], "");
    const urls = calls.map(([url]) => url);

    expect(urls).toContain(endpoints.buildings);
    expect(urls).toContain(endpoints.arrivals);
    expect(urls).not.toContain(endpoints.beds);
    expect(urls).not.toContain(endpoints.maintenance);
    expect(urls).not.toContain(endpoints.safety);
    expect(wrapper.find("[data-building-select]").exists()).toBe(true);
    expect(wrapper.text()).not.toContain("جاري تحميل المباني");
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
    expect(urls.filter((url) => url === endpoints.buildings)).toHaveLength(1);
    expect(wrapper.find("[data-building-select]").exists()).toBe(true);
    for (const allowed of ["/beds", "/maintenance", "/maintenance/new", "/custody", "/rounds"]) {
      expect(wrapper.find(`[data-to="${allowed}"]`).exists(), allowed).toBe(true);
    }
    expect(wrapper.find('[data-to="/arrivals"]').exists()).toBe(false);
    wrapper.unmount();
  });
});
