import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import InventoryCountPage from "./pages/InventoryCountPage.vue";
import { selectBuilding } from "./building.js";

const resources = vi.hoisted(() => ({ inventory: null, save: null }));

vi.mock("frappe-ui", async () => {
  const { reactive } = await import("vue");
  resources.inventory = reactive({ data: null, loading: false, error: null, fetch: null });
  resources.save = reactive({ loading: false, submit: vi.fn() });
  return {
    Button: { template: "<button><slot /></button>" },
    ErrorMessage: { props: ["message"], template: "<p>{{ message }}</p>" },
    FormControl: {
      props: ["modelValue", "label"],
      emits: ["update:modelValue"],
      template: "<input :value='modelValue' :aria-label='label' @input=\"$emit('update:modelValue', $event.target.value)\" />",
    },
    createResource: ({ url }) => (url.endsWith("submit_counts") ? resources.save : resources.inventory),
    toast: { create: vi.fn() },
  };
});

const items = [
  { name: "ROW-1", item_label: "بطانية", expected_quantity: 4 },
  { name: "ROW-2", item_label: "مخدة", expected_quantity: 2, counted_quantity: 1 },
];

describe("InventoryCountPage", () => {
  beforeEach(() => {
    Object.assign(resources.inventory, { data: null, loading: false, error: null });
    // The real resource sets data inside fetch and resolves afterwards, so Vue re-renders with
    // the new rows before the awaiting caller resumes.
    resources.inventory.fetch = vi.fn(async () => {
      resources.inventory.loading = true;
      await Promise.resolve();
      resources.inventory.data = { items: items.map((item) => ({ ...item })), conditions: ["Good"] };
      resources.inventory.loading = false;
      return resources.inventory.data;
    });
    resources.save.submit.mockReset();
    selectBuilding("BLD-0001");
  });

  async function mountSettled(options = {}) {
    const wrapper = mount(InventoryCountPage, {
      global: { stubs: { BuildingPicker: true }, ...options },
    });
    await nextTick();
    await nextTick();
    await nextTick();
    return wrapper;
  }

  it("renders every loaded row with its saved or expected quantity", async () => {
    const wrapper = await mountSettled();

    expect(resources.inventory.fetch).toHaveBeenCalled();
    const inputs = wrapper.findAll("input");
    expect(inputs).toHaveLength(items.length * 3);
    expect(inputs[0].element.value).toBe("4");
    expect(inputs[3].element.value).toBe("1");
  });

  it("drops the previous building's rows the moment the picker is cleared", async () => {
    const wrapper = await mountSettled();
    expect(wrapper.findAll("input")).toHaveLength(items.length * 3);

    selectBuilding("");
    await nextTick();
    await nextTick();

    expect(wrapper.findAll("input")).toHaveLength(0);
  });
});
