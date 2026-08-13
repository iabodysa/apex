import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

import { createWorkerGateway } from "./gateway.js";
import { workerRoutes } from "./routes.js";
import { createDraftAction } from "./asyncState.js";
import WorkerPage from "./WorkerPage.vue";

vi.mock("frappe-ui", () => ({
  Button: { template: "<button><slot /></button>" },
  FeatherIcon: { template: "<i />" },
}));

describe("Masar worker feature", () => {
  it("publishes only the canonical worker routes", () => {
    expect(workerRoutes.map((route) => route.path)).toEqual([
      "/home",
      "/transport",
      "/requests",
      "/profile",
      "/accommodation",
      "/custody",
      "/request-transport",
      "/requests/:name",
    ]);
    expect(workerRoutes.every((route) => route.feature === "worker")).toBe(true);
    expect(workerRoutes.every((route) => route.capability.startsWith("worker."))).toBe(true);
  });

  it("uses token-scoped endpoints without accepting a worker id", async () => {
    const call = vi.fn().mockResolvedValue({ message: { employee_name: "عامل تجريبي" } });
    const gateway = createWorkerGateway(call);

    await expect(gateway.home()).resolves.toEqual({ employee_name: "عامل تجريبي" });
    expect(call).toHaveBeenCalledWith("apex.salis.api.masar.get_worker_home");
    expect(JSON.stringify(call.mock.calls)).not.toContain("employee");
  });

  it("keeps entered values after a recoverable submission error", async () => {
    const action = createDraftAction({ subject: "", description: "" });
    action.draft.subject = "طلب صيانة";
    action.draft.description = "المكيف لا يعمل";

    await action.submit(vi.fn().mockRejectedValue(new Error("network")));

    expect(action.state.value).toBe("error");
    expect(action.draft).toEqual({ subject: "طلب صيانة", description: "المكيف لا يعمل" });
  });

  it("renders an empty state for an object containing an empty collection", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: "/requests",
        component: WorkerPage,
        meta: { view: { gateway: "requests", collections: ["items"], empty: "لا توجد طلبات." } },
      }],
    });
    await router.push("/requests");
    await router.isReady();
    const wrapper = mount(WorkerPage, {
      global: {
        plugins: [router],
        provide: { workerGateway: { requests: vi.fn().mockResolvedValue({ items: [] }) } },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("لا توجد طلبات.");
    expect(wrapper.find(".feature-details").exists()).toBe(false);
  });
});
