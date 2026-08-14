import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
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
  // Mirrors the real control: declared props stay props, every other attribute falls through
  // to the inner field rather than to the wrapper.
  FormControl: {
    inheritAttrs: false,
    props: ["modelValue", "label", "type", "rows"],
    emits: ["update:modelValue"],
    template: `
      <label><span>{{ label }}</span><textarea
        :value="modelValue"
        :rows="rows"
        v-bind="$attrs"
        @input="$emit('update:modelValue', $event.target.value)"
      /></label>
    `,
  },
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
      submit: vi.fn(async (params) => {
        resourceCalls.push([url, params]);
        const value = resourceData.get(url);
        if (value instanceof Error) throw value;
        return typeof value === "function" ? value(params) : value;
      }),
    };
  }),
  toast: { create: toastCreate },
}));

// The shape frappe-ui's frappeRequest actually throws: statusText-ish message, HTTP
// status only on response, and the clean server messages on messages.
function frappeError(status, messages) {
  const error = new Error("/api/method/apex.salis.api.masar.list_worker_requests ValidationError");
  error.response = { status };
  error.messages = messages;
  return error;
}

async function mountWorkerRoute(path) {
  const router = createRouter({ history: createMemoryHistory(), routes: workerRoutes });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(WorkerPage, { global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

describe("Masar worker feature", () => {
  beforeEach(() => {
    resourceData.clear();
    resourceCalls.length = 0;
  });

  it("reads the denial from response.status and shows the server message without a retry", async () => {
    resourceData.set(
      "apex.salis.api.masar.list_worker_requests",
      frappeError(403, ["لا تملك صلاحية عرض هذه الطلبات."]),
    );
    const wrapper = await mountWorkerRoute("/requests");

    const alert = wrapper.get("[role='alert']");
    expect(alert.get("h2").text()).toBe("تعذّر فتح الصفحة");
    expect(alert.text()).toContain("لا تملك صلاحية عرض هذه الطلبات.");
    expect(alert.text()).not.toContain("/api/method/");
    expect(alert.find("button").exists()).toBe(false);
    wrapper.unmount();
  });

  it("falls back to the denial wording when a 403 carries no server message", async () => {
    resourceData.set("apex.salis.api.masar.list_worker_requests", frappeError(403, []));
    const wrapper = await mountWorkerRoute("/requests");

    const alert = wrapper.get("[role='alert']");
    expect(alert.get("h2").text()).toBe("تعذّر فتح الصفحة");
    expect(alert.text()).toContain("لا تملك صلاحية عرض هذه الصفحة.");
    expect(alert.text()).not.toContain("/api/method/");
    wrapper.unmount();
  });

  it("keeps a retry and the server message for a retryable failure", async () => {
    resourceData.set(
      "apex.salis.api.masar.list_worker_requests",
      frappeError(500, ["تعذّر الوصول إلى الخادم."]),
    );
    const wrapper = await mountWorkerRoute("/requests");

    const alert = wrapper.get("[role='alert']");
    expect(alert.get("h2").text()).toBe("تعذّر تحميل الصفحة");
    expect(alert.text()).toContain("تعذّر الوصول إلى الخادم.");
    expect(alert.find("button").exists()).toBe(true);
    wrapper.unmount();
  });

  it("titles a worker request with the Arabic category instead of the stored enum key", async () => {
    resourceData.set("apex.salis.api.masar.list_worker_requests", {
      requests: [{ name: "RR-1", request_category: "Facility Item" }],
    });
    const wrapper = await mountWorkerRoute("/requests");

    expect(wrapper.text()).toContain("أثاث ومرافق");
    expect(wrapper.text()).not.toContain("Facility Item");
    wrapper.unmount();
  });

  it("keeps the transport server message and its retry instead of a fixed replacement", async () => {
    const failure = new Error("/api/method/apex.salis.api.masar.get_worker_transport");
    failure.response = { status: 500 };
    failure.messages = ["الخدمة متوقفة مؤقتاً."];
    resourceData.set("apex.salis.api.masar.get_worker_transport", failure);
    resourceData.set("apex.salis.api.boarding_flow.worker_trip_boarding", null);
    resourceData.set("apex.salis.api.masar.get_worker_context", { realtime_room: "" });
    const wrapper = mount(WorkerTransportPage, {
      global: { provide: { portalSubscribe: () => () => {}, workerGateway: {} } },
    });
    await flushPromises();

    const alert = wrapper.get("[role='alert']");
    expect(alert.get("h2").text()).toBe("تعذّر تحميل الرحلات");
    expect(alert.text()).toContain("الخدمة متوقفة مؤقتاً.");
    expect(alert.text()).not.toContain("/api/method/");
    expect(alert.find("button").exists()).toBe(true);
    wrapper.unmount();
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

  it("shows the shared record skeleton while a personal read is pending", async () => {
    resourceData.set("apex.salis.api.masar.get_worker_home", () => new Promise(() => {}));
    const router = createRouter({ history: createMemoryHistory(), routes: workerRoutes });
    await router.push("/home");
    await router.isReady();
    const wrapper = mount(WorkerPage, { global: { plugins: [router] } });

    expect(wrapper.find(".portal-skeleton").exists()).toBe(true);
    expect(wrapper.find(".feature-page__empty").exists()).toBe(false);
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

  it("keeps completed-trip rating page-local instead of routing it through the gateway", () => {
    const gateway = createWorkerGateway(vi.fn());
    expect(gateway).not.toHaveProperty("submitTripRating");
  });

  it("offers rating only for an unrated completed trip", async () => {
    resourceData.set("apex.salis.api.masar.get_worker_transport", {
      upcoming: [],
      past: [
        {
          transport_request: "TR-1",
          dispatch_trip: "DT-1",
          trip_status: "Completed",
          has_rated: false,
          pickup_point: "السكن",
        },
      ],
    });
    resourceData.set("apex.salis.api.boarding_flow.worker_trip_boarding", null);
    resourceData.set("apex.salis.api.masar.get_worker_context", { realtime_room: "" });
    resourceData.set("apex.salis.api.masar.submit_trip_rating", { status: "success" });
    const drafts = { read: vi.fn(() => null), write: vi.fn(), clear: vi.fn() };
    const wrapper = mount(WorkerTransportPage, {
      global: {
        provide: {
          portalSubscribe: () => () => {},
          workerGateway: {},
          portalDrafts: drafts,
        },
      },
    });
    await flushPromises();

    await wrapper.get("summary").trigger("click");
    await wrapper.get('[aria-label="5 نجوم"]').trigger("click");
    await wrapper.get('[data-rating-feedback="DT-1"]').setValue("رحلة ممتازة");
    await wrapper.get('[data-rating-submit="DT-1"]').trigger("click");
    await flushPromises();

    expect(resourceCalls).toContainEqual([
      "apex.salis.api.masar.submit_trip_rating",
      { dispatch_trip: "DT-1", rating: 5, feedback: "رحلة ممتازة" },
    ]);
    expect(wrapper.text()).toContain("تم إرسال تقييمك");
    expect(drafts.clear).toHaveBeenCalledWith("trip-rating-DT-1");
    wrapper.unmount();
  });

  it("restores, updates, and explicitly dismisses a subject-scoped trip rating draft", async () => {
    resourceData.set("apex.salis.api.masar.get_worker_transport", {
      upcoming: [],
      past: [{
        transport_request: "TR-1",
        dispatch_trip: "DT-1",
        trip_status: "Completed",
        has_rated: false,
      }],
    });
    resourceData.set("apex.salis.api.boarding_flow.worker_trip_boarding", null);
    resourceData.set("apex.salis.api.masar.get_worker_context", { realtime_room: "" });
    const drafts = {
      read: vi.fn(() => ({ rating: 4, feedback: "قيادة هادئة" })),
      write: vi.fn(),
      clear: vi.fn(),
    };
    const wrapper = mount(WorkerTransportPage, {
      global: {
        provide: {
          portalSubscribe: () => () => {},
          workerGateway: {},
          portalDrafts: drafts,
        },
      },
    });
    await flushPromises();
    await wrapper.get("summary").trigger("click");

    expect(wrapper.get('[aria-label="4 نجوم"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.get('[data-rating-feedback="DT-1"]').element.value).toBe("قيادة هادئة");
    await wrapper.get('[aria-label="5 نجوم"]').trigger("click");
    await wrapper.get('[data-rating-feedback="DT-1"]').setValue("ممتازة");
    expect(drafts.write).toHaveBeenLastCalledWith("trip-rating-DT-1", {
      rating: 5,
      feedback: "ممتازة",
    });

    await wrapper.get('[data-rating-dismiss="DT-1"]').trigger("click");
    expect(drafts.clear).toHaveBeenCalledWith("trip-rating-DT-1");
    expect(wrapper.get('[data-rating-feedback="DT-1"]').element.value).toBe("");
    wrapper.unmount();
  });

  it("localizes planned, dispatched, and completed trip states through the shared source", async () => {
    resourceData.set("apex.salis.api.masar.get_worker_transport", {
      upcoming: [
        { transport_request: "TR-1", trip_status: "Planned" },
        { transport_request: "TR-2", trip_status: "Dispatched" },
      ],
      past: [{ transport_request: "TR-3", trip_status: "Completed", has_rated: true }],
    });
    resourceData.set("apex.salis.api.boarding_flow.worker_trip_boarding", null);
    resourceData.set("apex.salis.api.masar.get_worker_context", { realtime_room: "" });
    const wrapper = mount(WorkerTransportPage, {
      global: { provide: { portalSubscribe: () => () => {}, workerGateway: {} } },
    });
    await flushPromises();
    await wrapper.get("summary").trigger("click");

    expect(wrapper.text()).toContain("مجدولة");
    expect(wrapper.text()).toContain("في الطريق");
    expect(wrapper.text()).toContain("مكتملة");
    wrapper.unmount();
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

  it("restores a subject-scoped draft, then clears storage and the live form without rewriting it", async () => {
    let saved = { subject: "طلب صيانة", description: "المكيف لا يعمل" };
    const store = {
      read: vi.fn(() => saved),
      write: vi.fn((_key, value) => { saved = value; }),
      clear: vi.fn(() => { saved = null; }),
    };
    const action = createDraftAction(
      { subject: "", description: "" },
      { store, key: "service-request" },
    );

    expect(action.draft).toEqual({ subject: "طلب صيانة", description: "المكيف لا يعمل" });
    action.draft.description = "المكيف لا يعمل منذ الصباح";
    await nextTick();
    expect(store.write).toHaveBeenLastCalledWith("service-request", {
      subject: "طلب صيانة",
      description: "المكيف لا يعمل منذ الصباح",
    });

    await action.submit(vi.fn().mockRejectedValue(new Error("network")));
    expect(store.clear).not.toHaveBeenCalled();
    store.write.mockClear();
    await action.submit(vi.fn().mockResolvedValue({ name: "REQ-1" }));
    expect(store.clear).toHaveBeenCalledWith("service-request");
    expect(action.draft).toEqual({ subject: "", description: "" });
    expect(store.write).not.toHaveBeenCalled();
  });

  it("explicitly discards a persisted draft and restores its declared defaults", async () => {
    const store = {
      read: vi.fn(() => ({ request_type: "Complaint", subject: "ضوضاء", description: "ليلاً" })),
      write: vi.fn(),
      clear: vi.fn(),
    };
    const action = createDraftAction(
      { request_type: "Maintenance", subject: "", description: "" },
      { store, key: "service-request" },
    );

    await action.discard();

    expect(action.draft).toEqual({
      request_type: "Maintenance",
      subject: "",
      description: "",
    });
    expect(action.dirty.value).toBe(false);
    expect(action.state.value).toBe("ready");
    expect(store.clear).toHaveBeenCalledWith("service-request");
    expect(store.write).not.toHaveBeenCalled();
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
