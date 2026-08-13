import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { createListResource } from "frappe-ui";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { supervisorRedirects, supervisorRoutes } from "./routes.js";
import SupervisorPage from "./SupervisorPage.vue";
import SupervisorCollection from "./components/SupervisorCollection.vue";

const { resourceData } = vi.hoisted(() => ({
  resourceData: new Map(),
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
  createListResource: vi.fn((options) => ({
    data: resourceData.get(`doctype:${options.doctype}`) || [],
    list: { loading: false, error: null },
    reload: vi.fn(),
  })),
  createDocumentResource: vi.fn(() => ({
    doc: null,
    get: { loading: false, error: null },
    reload: vi.fn(),
  })),
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

  it("centres operations on requests, recurring assignments and actual trips", () => {
    expect(supervisorRoutes.map((route) => route.path)).toEqual([
      "/requests",
      "/requests/:name",
      "/assignments",
      "/assignments/:name",
      "/trips",
      "/trips/:name",
      "/map",
      "/history",
    ]);
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
      ["/assignments", ["التشغيل المتكرر", ".supervisor-assignment-grid"]],
      ["/trips", ["الرحلات", ".supervisor-trip-board"]],
      ["/history", ["سجل الحركة", ".supervisor-history"]],
    ]);
    for (const [path, [title, layout]] of expectations) {
      const route = supervisorRoutes.find((candidate) => candidate.path === path);
      resourceData.set(`doctype:${route.meta.view.doctype}`, [{ name: `${path}-1` }]);
      const module = await route.component();
      const wrapper = mount(module.default);
      await flushPromises();

      expect(wrapper.get("h2").text()).toBe(title);
      expect(wrapper.find(layout).exists(), path).toBe(true);
      wrapper.unmount();
    }
  });

  it("declares human title fields for every operations collection", () => {
    const collectionRoutes = supervisorRoutes.filter(
      (route) => route.meta?.navigation && route.meta?.view?.doctype,
    );
    expect(collectionRoutes).not.toHaveLength(0);
    for (const route of collectionRoutes) {
      expect(route.meta.view.titleFields?.length, route.path).toBeGreaterThan(0);
      expect(route.meta.view.fallbackTitle, route.path).toBeTruthy();
    }
  });

  it("redirects legacy route-plan URLs to recurring assignments", () => {
    expect(supervisorRedirects).toEqual([
      { path: "/approvals", redirect: "/requests" },
      { path: "/routes", redirect: "/assignments" },
      { path: "/shifts", redirect: "/assignments" },
      { path: "/plans", redirect: "/assignments" },
      { path: "/plan/:name/:tab?", redirect: "/assignments" },
    ]);
  });

  it("keeps the live map on its specialized map component", () => {
    const mapRoute = supervisorRoutes.find((route) => route.path === "/map");
    expect(mapRoute.component.__name).toBe("TransportMapPage");
    expect(mapRoute.meta.navigation).toBe(true);
  });

  it("uses native Frappe resources for records and workflow", () => {
    const root = path.dirname(fileURLToPath(import.meta.url));
    const page = readFileSync(path.join(root, "SupervisorPage.vue"), "utf8");
    expect(page).toContain("createDocumentResource");
    expect(page).toContain("frappe.model.workflow.get_transitions");
    expect(page).toContain("frappe.model.workflow.apply_workflow");
    expect(page).toMatch(
      /url: "frappe\.model\.workflow\.get_transitions",\s+method: "POST"/,
    );
    for (const name of [
      "TransportRequestsPage.vue",
      "RouteAssignmentsPage.vue",
      "DispatchTripsPage.vue",
      "MovementHistoryPage.vue",
    ]) {
      const source = readFileSync(path.join(root, "pages", name), "utf8");
      expect(source, name).toContain("createListResource");
      expect(source, name).not.toContain("route_supervisor.get_");
    }
  });

  it("requests human Link titles and protects a missing passenger name", () => {
    const root = path.dirname(fileURLToPath(import.meta.url));
    for (const name of ["RouteAssignmentsPage.vue", "DispatchTripsPage.vue", "MovementHistoryPage.vue"]) {
      const source = readFileSync(path.join(root, "pages", name), "utf8");
      expect(source, name).toMatch(/project\.project_name as project_label/);
      expect(source, name).toMatch(/driver\.full_name as driver_label/);
      expect(source, name).toMatch(/vehicle\.plate_number as vehicle_label/);
    }
    expect(readFileSync(path.join(root, "SupervisorPage.vue"), "utf8"))
      .toContain("passenger.passenger_name || 'راكب غير مسمى'");
    const requests = readFileSync(path.join(root, "pages", "TransportRequestsPage.vue"), "utf8");
    expect(requests).toMatch(/project\.project_name as project_label/);
    expect(requests).toMatch(/assigned_to_trip\.trip_title as assigned_trip_label/);
    expect(requests).toContain("request.assigned_trip_label || 'رحلة مسندة'");
    const assignments = readFileSync(path.join(root, "pages", "RouteAssignmentsPage.vue"), "utf8");
    expect(assignments).toMatch(/work_shift\.shift_name as work_shift_label/);
    expect(assignments).toMatch(/assignment\.shift_name \|\| assignment\.work_shift_label \|\| 'غير محدد'/);
    for (const name of ["DispatchTripsPage.vue", "MovementHistoryPage.vue"]) {
      const source = readFileSync(path.join(root, "pages", name), "utf8");
      expect(source, name).toContain("trip.route_template_label");
      expect(source, name).toContain("trip.route_assignment_label");
      expect(source, name).not.toMatch(/trip\.(driver|vehicle|project|route_template|route_assignment) \|\|/);
    }
  });

  it("uses the exact status options declared by the current DocType metadata", () => {
    const root = path.dirname(fileURLToPath(import.meta.url));
    const assignments = readFileSync(path.join(root, "pages", "RouteAssignmentsPage.vue"), "utf8");
    for (const value of ["Pending", "Approved", "Rejected", "Cancelled"]) {
      expect(assignments).toContain(`value: '${value}'`);
    }
    expect(assignments).not.toContain("value: 'Active'");
    expect(assignments).not.toContain("value: 'Inactive'");

    const requests = readFileSync(path.join(root, "pages", "TransportRequestsPage.vue"), "utf8");
    for (const value of ["New", "Validated", "Approved", "Scheduled", "Fulfilled", "Rejected", "Cancelled"]) {
      expect(requests).toContain(`value: '${value}'`);
    }
  });

  it("resets native list pagination before reloading changed URL filters", async () => {
    const update = vi.fn(function (options) { Object.assign(resource, options); });
    const reload = vi.fn().mockResolvedValue(undefined);
    const resource = {
      data: [{ name: "ROW-1" }],
      list: { loading: false, error: null },
      start: 0,
      pageLength: 20,
      hasNextPage: true,
      update,
      reload,
      next: vi.fn(function () { resource.start += resource.pageLength; }),
    };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: { template: "<div />" } }],
    });
    await router.push("/");
    await router.isReady();
    const wrapper = mount(SupervisorCollection, {
      props: {
        title: "طلبات النقل",
        description: "الوصف",
        icon: "inbox",
        resource,
        empty: "فارغ",
      },
      global: { plugins: [router] },
      slots: { default: "<div />" },
    });
    await flushPromises();

    resource.next();
    expect(resource.start).toBe(20);
    update.mockClear();
    reload.mockClear();
    await router.push("/?status=Approved");
    await flushPromises();

    expect(update).toHaveBeenLastCalledWith(expect.objectContaining({
      start: 0,
      filters: { status: "Approved" },
    }));
    expect(resource.start).toBe(0);
    expect(reload).toHaveBeenCalledOnce();
    wrapper.unmount();
  });

  it("renders a clear missing-record state on a native detail route", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: "/requests",
          component: SupervisorPage,
          meta: {
            view: {
              doctype: "Route Assignment",
              title: "تفاصيل التشغيل المتكرر",
            },
          },
        },
      ],
    });
    await router.push("/requests");
    await router.isReady();
    const wrapper = mount(SupervisorPage, {
      global: {
        plugins: [router],
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("السجل غير موجود.");
    expect(wrapper.find(".feature-details").exists()).toBe(false);
  });
});
