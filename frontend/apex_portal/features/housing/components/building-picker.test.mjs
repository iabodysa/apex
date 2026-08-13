import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import BuildingPicker from "./BuildingPicker.vue";

const { resource } = vi.hoisted(() => ({
  resource: { data: [], loading: false, error: null, fetch: vi.fn() },
}));

vi.mock("frappe-ui", () => ({
  Button: { props: ["label"], template: "<button>{{ label }}</button>" },
  Select: { template: "<select />" },
  createResource: () => resource,
}));

describe("BuildingPicker", () => {
  beforeEach(() => {
    resource.data = [];
    resource.loading = false;
    resource.error = null;
    resource.fetch.mockReset().mockResolvedValue([]);
  });

  it("distinguishes loading, error, and empty building states", async () => {
    resource.loading = true;
    const loading = mount(BuildingPicker);
    expect(loading.text()).toContain("جاري تحميل المباني");
    loading.unmount();

    resource.loading = false;
    resource.error = new Error("network");
    const failed = mount(BuildingPicker);
    expect(failed.text()).toContain("تعذر تحميل المباني");
    await failed.get("button").trigger("click");
    expect(resource.fetch).toHaveBeenCalled();
    failed.unmount();

    resource.error = null;
    const empty = mount(BuildingPicker);
    expect(empty.text()).toContain("لا توجد مبانٍ متاحة");
    expect(empty.find("select").exists()).toBe(false);
  });
});
