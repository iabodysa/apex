import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { createTransportSupervisorGateway } from "./gateway.js";
import { supervisorRedirects, supervisorRoutes } from "./routes.js";
import SupervisorPage from "./SupervisorPage.vue";

vi.mock("frappe-ui", () => ({
  Badge: { template: "<span />" },
  Button: { template: "<button><slot /></button>" },
  FeatherIcon: { template: "<i />" },
}));

describe("Masar transport supervisor feature", () => {
  it("keeps map view, Leaflet, state, styles, and server access in focused files", () => {
    const root = path.dirname(fileURLToPath(import.meta.url));
    for (const name of ["leafletAdapter.js", "transportMapState.js", "styles.css", "gateway.js"]) {
      expect(existsSync(path.join(root, name))).toBe(true);
    }
    const page = readFileSync(path.join(root, "TransportMapPage.vue"), "utf8");
    expect(page).toContain('from "./leafletAdapter.js"');
    expect(page).toContain('from "./transportMapState.js"');
    expect(page).toContain('import "./styles.css"');
    expect(page).not.toMatch(/window\.L|document\.createElement|L\.map|L\.tileLayer|<style/);
  });

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

  it("keeps the live map on its specialized map component", () => {
    const mapRoute = supervisorRoutes.find((route) => route.path === "/map");
    expect(mapRoute.component.__name).toBe("TransportMapPage");
    expect(mapRoute.meta.navigation).toBe(true);
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

  it("keeps active driver positions behind the supervisor gateway", async () => {
    const call = vi.fn().mockResolvedValue({ message: { positions: [] } });
    const gateway = createTransportSupervisorGateway(call);
    await expect(gateway.map()).resolves.toEqual({ positions: [] });
    expect(call).toHaveBeenCalledWith("apex.salis.api.route_supervisor.get_active_driver_positions");
  });

  it("renders an empty state for an object containing an empty collection", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: "/requests",
        component: SupervisorPage,
        meta: { view: { gateway: "requests", collections: ["items"], empty: "لا توجد عمليات." } },
      }],
    });
    await router.push("/requests");
    await router.isReady();
    const wrapper = mount(SupervisorPage, {
      global: {
        plugins: [router],
        provide: { transportSupervisorGateway: { requests: vi.fn().mockResolvedValue({ items: [] }) } },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("لا توجد عمليات.");
    expect(wrapper.find(".feature-details").exists()).toBe(false);
  });
});
