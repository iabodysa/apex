import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { createListResource } from "frappe-ui";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { supervisorRedirects, supervisorRoutes } from "./routes.js";
import RoutePlanForm from "./RoutePlanForm.vue";
import SupervisorPage from "./SupervisorPage.vue";

const { resourceData, insertPlan } = vi.hoisted(() => ({
  resourceData: new Map(),
  insertPlan: vi.fn().mockResolvedValue({ name: "RP-1" }),
}));

vi.mock("frappe-ui", () => ({
  Badge: { template: "<span />" },
  Button: { template: "<button><slot /></button>" },
  FeatherIcon: { template: "<i />" },
  FormControl: { template: "<input />" },
  createResource: vi.fn((options) => {
    let url = options.url;
    return {
      data: resourceData.get(url),
      error: null,
      loading: false,
      url,
      update(next) {
        if (next.url) {
          url = next.url;
          this.url = next.url;
          this.data = resourceData.get(next.url);
        }
      },
      fetch: vi.fn(async function (params) {
        const value = resourceData.get(url);
        if (value instanceof Error) throw value;
        this.data = typeof value === "function" ? value(params) : value;
        return this.data;
      }),
    };
  }),
  createListResource: vi.fn(() => ({ insert: { submit: insertPlan } })),
}));

describe("Masar transport supervisor feature", () => {
  it("keeps map view, Leaflet, state, styles, and server access in focused files", () => {
    const root = path.dirname(fileURLToPath(import.meta.url));
    for (const name of ["leafletAdapter.js", "transportMapState.js", "styles.css"]) {
      expect(existsSync(path.join(root, name))).toBe(true);
    }
    expect(existsSync(path.join(root, "gateway.js"))).toBe(false);
    const page = readFileSync(path.join(root, "TransportMapPage.vue"), "utf8");
    expect(page).toContain('from "./leafletAdapter.js"');
    expect(page).toContain('from "./transportMapState.js"');
    expect(page).toContain('import "./styles.css"');
    expect(page).toContain("createResource");
    expect(page).toContain("apex.salis.api.route_supervisor.get_active_driver_positions");
    expect(page).not.toContain("transportSupervisorGateway");
    expect(page).toMatch(/<Button[^>]*icon-left="refresh-cw"[^>]*>تحديث<\/Button>/);
    expect(page).not.toMatch(/window\.L|document\.createElement|L\.map|L\.tileLayer|<style/);
  });

  it("centres operations on requests, shifts, plans and dispatch trips", () => {
    expect(supervisorRoutes.map((route) => route.path)).toEqual(["/requests", "/shifts", "/plans", "/plans/new", "/plans/:name", "/trips", "/trips/:name", "/map", "/history"]);
  });

  it("gives every sidebar destination its own page component", () => {
    const navigationRoutes = supervisorRoutes.filter((route) => route.meta.navigation);

    expect(new Set(navigationRoutes.map((route) => route.component)).size).toBe(
      navigationRoutes.length,
    );
  });

  it("renders a distinct operations layout for every list destination", async () => {
    const expectations = new Map([
      ["/requests", ["طلبات النقل", ".supervisor-request-queue"]],
      ["/shifts", ["الشفتات", ".supervisor-shift-grid"]],
      ["/plans", ["خطط المسار", ".supervisor-plan-grid"]],
      ["/trips", ["الرحلات", ".supervisor-trip-board"]],
      ["/history", ["سجل الحركة", ".supervisor-history"]],
    ]);
    for (const [path, [title, layout]] of expectations) {
      const route = supervisorRoutes.find((candidate) => candidate.path === path);
      resourceData.set(route.meta.view.endpoint, [{ name: `${path}-1` }]);
      const module = await route.component();
      const wrapper = mount(module.default);
      await flushPromises();

      expect(wrapper.get("h2").text()).toBe(title);
      expect(wrapper.find(layout).exists(), path).toBe(true);
      wrapper.unmount();
    }
  });

  it("declares human title fields for every operations collection", () => {
    const collectionRoutes = supervisorRoutes.filter((route) => route.meta?.view?.collections);
    expect(collectionRoutes).not.toHaveLength(0);
    for (const route of collectionRoutes) {
      expect(route.meta.view.titleFields?.length, route.path).toBeGreaterThan(0);
      expect(route.meta.view.fallbackTitle, route.path).toBeTruthy();
    }
  });

  it("preserves the legacy hash redirects", () => {
    expect(supervisorRedirects).toEqual([
      { path: "/approvals", redirect: "/requests" },
      { path: "/routes", redirect: "/plans" },
      { path: "/plan/:name/:tab?", redirect: expect.any(Function) },
    ]);
    expect(supervisorRedirects[2].redirect({ params: { name: "RP-1" } })).toBe("/plans/RP-1");
  });

  it("keeps the live map on its specialized map component", () => {
    const mapRoute = supervisorRoutes.find((route) => route.path === "/map");
    expect(mapRoute.component.__name).toBe("TransportMapPage");
    expect(mapRoute.meta.navigation).toBe(true);
  });

  it("uses the native Route Plan insert resource on the create page", async () => {
    insertPlan.mockClear();
    const wrapper = mount(RoutePlanForm);

    await wrapper.get("form").trigger("submit");

    expect(createListResource).toHaveBeenCalledWith({
      doctype: "Route Plan",
      auto: false,
    });
    expect(insertPlan).toHaveBeenCalledWith({
      route_name: "",
      project: "",
      shift: "",
      driver: "",
      vehicle: "",
    });
  });

  it("renders an empty state for an object containing an empty collection", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: "/requests",
          component: SupervisorPage,
          meta: {
            view: {
              endpoint: "apex.test.supervisor.requests",
              collections: ["items"],
              empty: "لا توجد عمليات.",
            },
          },
        },
      ],
    });
    resourceData.set("apex.test.supervisor.requests", { items: [] });
    await router.push("/requests");
    await router.isReady();
    const wrapper = mount(SupervisorPage, {
      global: {
        plugins: [router],
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("لا توجد عمليات.");
    expect(wrapper.find(".feature-details").exists()).toBe(false);
  });
});
