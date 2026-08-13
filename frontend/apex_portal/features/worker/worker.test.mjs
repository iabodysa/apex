import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

import { createWorkerGateway } from "./gateway.js";
import { workerRoutes } from "./routes.js";
import { createDraftAction } from "./asyncState.js";
import WorkerPage from "./WorkerPage.vue";
import WorkerTransportPage from "./WorkerTransportPage.vue";

const { resourceData, resourceCalls, toastCreate } = vi.hoisted(() => ({
  resourceData: new Map(),
  resourceCalls: [],
  toastCreate: vi.fn(),
}));

vi.mock("frappe-ui", () => ({
  Badge: { props: ["label"], template: "<span>{{ label }}</span>" },
  Button: { template: "<button><slot /></button>" },
  ErrorMessage: { props: ["message"], template: "<p>{{ message }}</p>" },
  FeatherIcon: { template: "<i />" },
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
  toast: { create: toastCreate },
}));

describe("Masar worker feature", () => {
  beforeEach(() => {
    resourceData.clear();
    resourceCalls.length = 0;
  });

  it("publishes only the canonical worker routes", () => {
    expect(workerRoutes.map((route) => route.path)).toEqual(["/home", "/transport", "/requests", "/profile", "/accommodation", "/custody", "/request-transport", "/requests/:name"]);
    expect(workerRoutes.every((route) => route.feature === "worker")).toBe(true);
    expect(workerRoutes.every((route) => route.capability.startsWith("worker."))).toBe(true);
  });

  it("uses a page-local token-scoped home resource without a worker id", async () => {
    resourceData.set("apex.salis.api.masar.get_worker_home", {
      profile: { employee_name: "عامل تجريبي" },
    });
    resourceCalls.length = 0;
    const router = createRouter({
      history: createMemoryHistory(),
      routes: workerRoutes,
    });
    await router.push("/home");
    await router.isReady();
    const wrapper = mount(WorkerPage, { global: { plugins: [router] } });
    await flushPromises();

    expect(resourceCalls).toContainEqual(["apex.salis.api.masar.get_worker_home", undefined]);
    expect(JSON.stringify(resourceCalls)).not.toContain("employee_id");
    wrapper.unmount();
  });

  it("keeps the archived boarding journey on the dedicated transport screen", async () => {
    const transport = workerRoutes.find((route) => route.path === "/transport");
    expect(transport.component).toBe(WorkerTransportPage);

    const call = vi.fn().mockResolvedValue({ message: {} });
    const gateway = createWorkerGateway(call);
    await gateway.requestWait();
    await gateway.claimBoarded();

    expect(call.mock.calls).toEqual([["apex.salis.api.boarding_flow.worker_request_wait"], ["apex.salis.api.boarding_flow.worker_claim_boarded"]]);
  });

  it("shows the active wait quota and driver reminder window", async () => {
    toastCreate.mockReset();
    const now = new Date(Date.now() - 30_000).toISOString();
    resourceData.set("apex.salis.api.masar.get_worker_transport", {
      upcoming: [],
      past: [],
    });
    resourceData.set("apex.salis.api.boarding_flow.worker_trip_boarding", {
      dispatch_trip: "DT-1",
      status: "Pending",
      wait_count: 1,
      wait_max: 3,
      wait_at: now,
      wait_window_seconds: 120,
      notify_at: now,
      notify_window_seconds: 120,
      boarding_window: { state: "at_stop", can_confirm: true },
    });
    resourceData.set("apex.salis.api.masar.get_worker_context", {
      realtime_room: "",
    });
    const requestWait = vi.fn().mockResolvedValue({});
    const wrapper = mount(WorkerTransportPage, {
      global: {
        provide: {
          portalSubscribe: () => () => {},
          workerGateway: {
            requestWait,
          },
        },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("طلب الانتظار 1 من 3");
    expect(wrapper.text()).toContain("السائق نبهك");
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(requestWait).toHaveBeenCalledOnce();
    expect(toastCreate).toHaveBeenCalledWith({
      type: "success",
      message: "وصل طلب الانتظار إلى السائق",
    });
    wrapper.unmount();
  });

  it("keeps entered values after a recoverable submission error", async () => {
    const action = createDraftAction({ subject: "", description: "" });
    action.draft.subject = "طلب صيانة";
    action.draft.description = "المكيف لا يعمل";

    await action.submit(vi.fn().mockRejectedValue(new Error("network")));

    expect(action.state.value).toBe("error");
    expect(action.draft).toEqual({
      subject: "طلب صيانة",
      description: "المكيف لا يعمل",
    });
  });

  it("renders an empty state for an object containing an empty collection", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: "/requests",
          component: WorkerPage,
          meta: {
            view: {
              endpoint: "apex.test.worker.requests",
              collections: ["items"],
              empty: "لا توجد طلبات.",
            },
          },
        },
      ],
    });
    resourceData.set("apex.test.worker.requests", { items: [] });
    await router.push("/requests");
    await router.isReady();
    const wrapper = mount(WorkerPage, {
      global: {
        plugins: [router],
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("لا توجد طلبات.");
    expect(wrapper.find(".feature-details").exists()).toBe(false);
  });
});
