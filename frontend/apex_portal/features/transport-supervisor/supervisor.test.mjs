import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { createDocumentResource, createListResource } from "frappe-ui";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { supervisorRedirects, supervisorRoutes } from "./routes.js";
import SupervisorPage from "./SupervisorPage.vue";
import SupervisorCollection from "./components/SupervisorCollection.vue";
import SupervisorRecordCollections from "./components/SupervisorRecordCollections.vue";

const { resourceData } = vi.hoisted(() => ({
  resourceData: new Map(),
}));

vi.mock("frappe-ui", () => ({
  Badge: { template: "<span />" },
  Button: { template: "<button><slot /></button>" },
  FormControl: {
    name: "FormControl",
    props: ["modelValue", "label", "type", "options"],
    template: "<input />",
  },
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

vi.mock("frappe-ui/frappe", () => ({
  Link: {
    name: "FrappeLink",
    props: ["modelValue", "doctype", "label", "placeholder"],
    emits: ["update:modelValue"],
    template: "<div />",
  },
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
    expect(page).toMatch(/<Button[^>]*icon-left="lucide-refresh-cw"[^>]*>تحديث<\/Button>/);
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

  it("groups every mobile destination by its operational task hierarchy", () => {
    const navigation = supervisorRoutes.filter((route) => route.meta.navigation);
    expect(navigation.every((route) => route.meta.group)).toBe(true);
    expect(navigation.map((route) => route.meta.group)).toEqual([
      "الطلبات",
      "التخطيط",
      "التشغيل المباشر",
      "التشغيل المباشر",
      "السجل",
    ]);
    expect(navigation.map((route) => route.meta.group)).not.toContain("أخرى");
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
    expect(readFileSync(path.join(root, "components", "SupervisorRecordCollections.vue"), "utf8"))
      .toContain("passenger.passenger_name || 'راكب غير مسمى'");
    const detail = readFileSync(path.join(root, "SupervisorPage.vue"), "utf8");
    expect(readFileSync(path.join(root, "components", "SupervisorRecordFacts.vue"), "utf8"))
      .toContain("frappe.client.get_value");
    expect(detail).toContain("meaningfulRequestTitle");
    for (const field of ["work_shift", "route_template", "project", "driver", "vehicle", "requested_by", "assigned_to_trip"]) {
      expect(readFileSync(path.join(root, "routes.js"), "utf8"), field).toContain(`key: "${field}"`);
    }
    const requests = readFileSync(path.join(root, "pages", "TransportRequestsPage.vue"), "utf8");
    expect(requests).toMatch(/project\.project_name as project_label/);
    expect(requests).toMatch(/assigned_to_trip\.trip_title as assigned_trip_label/);
    expect(requests).toContain("request.accommodation_building_label");
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
    const routes = readFileSync(path.join(root, "routes.js"), "utf8");
    expect(routes).toContain('key: "accommodation_building"');
    expect(routes).toContain('labelKey: "accommodation_building_label"');
  });

  it("delegates project search beyond the current page to Frappe's native Link control", async () => {
    const resource = {
      data: [{ name: "DT-1", project: "PROJ-1", project_label: "مشروع المطار" }],
      list: { loading: false, error: null },
      update: vi.fn(),
      reload: vi.fn(),
    };
    const wrapper = mount(SupervisorCollection, {
      props: {
        title: "الرحلات",
        description: "الوصف",
        icon: "lucide-navigation",
        resource,
        empty: "فارغ",
      },
      slots: { default: "<div />" },
    });
    await flushPromises();

    const projectFilter = wrapper.getComponent({ name: "FrappeLink" });
    expect(projectFilter.props("doctype")).toBe("Project");
    await projectFilter.vm.$emit("update:modelValue", "PROJ-99");
    await flushPromises();
    expect(projectFilter.props("modelValue")).toBe("PROJ-99");
    wrapper.unmount();
  });

  it("uses the exact status options declared by the current DocType metadata", () => {
    const root = path.dirname(fileURLToPath(import.meta.url));
    const assignments = readFileSync(path.join(root, "pages", "RouteAssignmentsPage.vue"), "utf8");
    expect(assignments).toContain('statusOptions(["Pending", "Approved", "Rejected", "Cancelled"])');
    expect(assignments).not.toContain('"Active"');
    expect(assignments).not.toContain('"Inactive"');

    const requests = readFileSync(path.join(root, "pages", "TransportRequestsPage.vue"), "utf8");
    expect(requests).toMatch(/statusOptions\(\[\s*"New", "Validated", "Approved", "Scheduled", "Fulfilled", "Rejected", "Cancelled",?\s*\]\)/);
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
        icon: "lucide-inbox",
        resource,
        empty: "فارغ",
        statusOptions: [{ label: "معتمد", value: "Approved" }],
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

  it("serializes route refreshes so the latest filter always wins", async () => {
    let releaseFirst;
    const update = vi.fn(function (options) { Object.assign(resource, options); });
    const reload = vi.fn().mockResolvedValue(undefined);
    const resource = {
      data: [{ name: "ROW-1" }],
      list: { loading: false, error: null },
      update,
      reload,
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
        icon: "lucide-inbox",
        resource,
        empty: "فارغ",
        statusOptions: [{ label: "معتمد", value: "Approved" }],
      },
      global: { plugins: [router] },
    });
    await flushPromises();

    reload.mockReset();
    reload
      .mockImplementationOnce(() => new Promise((resolve) => { releaseFirst = resolve; }))
      .mockResolvedValue(undefined);
    await router.push("/?status=Approved");
    await flushPromises();
    await router.push("/?project=PROJ-2");
    await flushPromises();

    expect(reload).toHaveBeenCalledOnce();
    releaseFirst();
    await flushPromises();
    expect(reload).toHaveBeenCalledTimes(2);
    expect(resource.filters).toEqual({ project: "PROJ-2" });
    wrapper.unmount();
  });

  it.each([
    ["/trips?status=Completed", { status: ["not in", ["Completed", "Cancelled"]] }, ["Planned", "Dispatched"]],
    ["/history?status=Planned", { status: ["in", ["Completed", "Cancelled"]] }, ["Completed", "Cancelled"]],
  ])("keeps %s inside its route-owned status scope", async (location, baseFilters, allowed) => {
    const update = vi.fn();
    const resource = {
      data: [],
      list: { loading: false, error: null },
      update,
      reload: vi.fn().mockResolvedValue(undefined),
    };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/trips", component: { template: "<div />" } },
        { path: "/history", component: { template: "<div />" } },
      ],
    });
    await router.push(location);
    await router.isReady();
    const wrapper = mount(SupervisorCollection, {
      props: {
        title: "الرحلات",
        description: "الوصف",
        icon: "lucide-navigation",
        resource,
        empty: "فارغ",
        baseFilters,
        statusOptions: allowed.map((value) => ({ value, label: value })),
      },
      global: { plugins: [router] },
    });
    await flushPromises();

    expect(update).toHaveBeenLastCalledWith(expect.objectContaining({ filters: baseFilters }));
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

  it("refuses a request the supervisor may not read, and offers no retry for the refusal", async () => {
    createDocumentResource.mockReturnValueOnce({
      doc: null,
      get: { loading: false, error: { status: 403 } },
      reload: vi.fn(),
    });
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: "/requests/:name",
          component: SupervisorPage,
          meta: { view: { doctype: "Transport Request", title: "تفاصيل طلب النقل" } },
        },
      ],
    });
    await router.push("/requests/TR-DENIED");
    await router.isReady();
    const wrapper = mount(SupervisorPage, { global: { plugins: [router] } });
    await flushPromises();

    expect(wrapper.text()).toContain("تعذّر فتح السجل");
    expect(wrapper.text()).toContain("لا تملك صلاحية هذا السجل.");
    expect(wrapper.text()).not.toContain("إعادة المحاولة");
    expect(wrapper.find(".supervisor-request-assignment").exists()).toBe(false);
    expect(wrapper.find(".request-trip-planning").exists()).toBe(false);
    wrapper.unmount();
  });

  it("keeps the record-type planning panel between the assigned requests and the passenger list", () => {
    const wrapper = mount(SupervisorRecordCollections, {
      props: {
        stops: [{ name: "STOP-1", stop_name: "بوابة السكن" }],
        assignedRequests: [{ name: "AR-1", transport_request: "TR-1" }],
        passengers: [{ name: "PS-1", passenger_name: "عامل العرض" }],
      },
      slots: { default: '<section class="planning-panel" />' },
    });
    const html = wrapper.html();

    expect(html.indexOf("supervisor-stop-list")).toBeLessThan(html.indexOf("supervisor-assigned-list"));
    expect(html.indexOf("supervisor-assigned-list")).toBeLessThan(html.indexOf("planning-panel"));
    expect(html.indexOf("planning-panel")).toBeLessThan(html.indexOf("supervisor-passenger-list"));
    wrapper.unmount();
  });

  it("exposes request planning and atomic multi-request trip assignment on the detail surfaces", () => {
    const root = path.dirname(fileURLToPath(import.meta.url));
    const detail = readFileSync(path.join(root, "SupervisorPage.vue"), "utf8");
    const tripAssignment = readFileSync(path.join(root, "components", "TripRequestAssignment.vue"), "utf8");
    const requestPlanning = readFileSync(path.join(root, "components", "RequestTripPlanning.vue"), "utf8");

    expect(detail).toContain("RequestTripPlanning");
    expect(tripAssignment).toContain("buildTripAssignments");
    expect(tripAssignment).toContain('type="checkbox"');
    expect(requestPlanning).toContain("assign_requests_to_trip");
    expect(requestPlanning).toContain("create_ad_hoc_trip");
    expect(requestPlanning).toContain("اعتمد الطلب أولاً");
  });
});
