import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

const { document } = vi.hoisted(() => ({
  document: { doc: null, get: { loading: false, error: null }, reload: vi.fn() },
}));

vi.mock("frappe-ui", () => ({
  Badge: { props: ["label"], template: "<span>{{ label }}</span>" },
  Button: { template: "<button><slot /></button>" },
  createDocumentResource: vi.fn(() => document),
}));

import HandoverDetailPage from "./pages/HandoverDetailPage.vue";

async function mountHandover(error) {
  document.doc = null;
  document.get = { loading: false, error };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/handovers/:name", component: HandoverDetailPage }],
  });
  await router.push("/handovers/VH-1");
  await router.isReady();
  const wrapper = mount(HandoverDetailPage, { global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

describe("HandoverDetailPage error contract", () => {
  it("shows the server message and hides the retry on a permission denial", async () => {
    const wrapper = await mountHandover({
      message: 'Traceback: File "/home/frappe/apps/apex/private.py", line 4',
      response: { status: 403 },
      messages: ["لا تملك صلاحية عرض تسليم المركبة."],
    });

    const alert = wrapper.get("[role='alert']");
    expect(alert.text()).toContain("لا تملك صلاحية عرض تسليم المركبة.");
    expect(alert.text()).not.toContain("Traceback");
    expect(alert.find("button").exists()).toBe(false);
    wrapper.unmount();
  });

  it("keeps the retry for a retryable failure", async () => {
    const wrapper = await mountHandover({
      response: { status: 500 },
      messages: ["تعذّر الوصول إلى الخادم."],
    });

    const alert = wrapper.get("[role='alert']");
    expect(alert.text()).toContain("تعذّر الوصول إلى الخادم.");
    expect(alert.find("button").exists()).toBe(true);
    wrapper.unmount();
  });
});
