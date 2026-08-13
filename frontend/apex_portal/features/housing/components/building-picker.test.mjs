import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import BuildingPicker from "./BuildingPicker.vue";
import { building, selectBuilding } from "../building.js";

const { resource, createResource } = vi.hoisted(() => {
  const resource = { data: [], loading: false, error: null, fetch: vi.fn() };
  return { resource, createResource: vi.fn(() => resource) };
});

vi.mock("frappe-ui", () => ({
  Button: { props: ["label"], template: "<button>{{ label }}</button>" },
  Select: { template: "<select />" },
  createResource,
}));

describe("BuildingPicker", () => {
  beforeEach(() => {
    globalThis.window.apex_portal = { capabilities: ["estate_read"] };
    resource.data = [];
    resource.loading = false;
    resource.error = null;
    resource.fetch.mockReset().mockResolvedValue([]);
    createResource.mockClear();
    selectBuilding("");
  });

  afterEach(() => {
    delete globalThis.window.apex_portal;
    selectBuilding("");
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

  it("loads scoped buildings for check-in without estate portfolio access", async () => {
    globalThis.window.apex_portal = { capabilities: ["check_in"] };
    const wrapper = mount(BuildingPicker);
    await flushPromises();

    expect(wrapper.text()).toContain("لا توجد مبانٍ متاحة");
    expect(wrapper.find("select").exists()).toBe(false);
    expect(createResource).toHaveBeenCalledOnce();
    expect(resource.fetch).toHaveBeenCalledOnce();
  });

  it("reads a parent-owned resource without issuing its own request", async () => {
    const owned = {
      data: [{ building: "BLD-9", building_title: "سكن الجنوب" }],
      loading: false,
      error: null,
      fetch: vi.fn(),
    };
    const wrapper = mount(BuildingPicker, { props: { resource: owned } });
    await flushPromises();

    expect(createResource).not.toHaveBeenCalled();
    expect(owned.fetch).not.toHaveBeenCalled();
    expect(wrapper.find("select").exists()).toBe(true);
    expect(building.value).toBe("BLD-9");
  });
});
