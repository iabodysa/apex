import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const { stub, reload } = vi.hoisted(() => ({ stub: {}, reload: vi.fn() }));

vi.mock("frappe-ui", async () => {
  const { reactive } = await import("vue");
  // The component reads these flags in its template, so the stub has to be reactive the way the
  // real resource is — a plain object would leave the first render on screen forever.
  // `list.fetched` is the flag the real resource sets only after a request resolves without
  // throwing (node_modules/frappe-ui/src/resources/resources.js:107), which is what separates
  // "nothing to assign" from "we have not been told yet".
  //
  // The reactive object is held on a property rather than Object.assign-ed onto the hoisted one:
  // createListResource returns reactive(...) whole
  // (node_modules/frappe-ui/src/resources/listResource.js:36), so `data` is a tracked dependency,
  // and flattening it onto a plain object dropped that. A computed over `requests.data` then
  // cached its first value and never invalidated, so this file passed only for as long as nothing
  // read the derived list before the rows landed.
  stub.resource = reactive({
    data: null,
    list: { fetched: false, loading: false },
    hasNextPage: false,
    start: 0,
    pageLength: 50,
    update: () => {},
    reload,
  });
  return {
    Button: {
      props: ["type", "disabled"],
      template: '<button :type="type || \'button\'" :disabled="disabled"><slot /></button>',
    },
    FormControl: {
      props: ["modelValue", "label", "type", "options"],
      emits: ["update:modelValue"],
      template: '<label>{{ label }}<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" /></label>',
    },
    createListResource: () => stub.resource,
    createResource: () => ({ submit: async () => ({}) }),
  };
});

import TripRequestAssignment from "./components/TripRequestAssignment.vue";

const EMPTY_MESSAGE = "لا توجد طلبات معتمدة جاهزة للإسناد.";
const trip = { name: "DT-000876", stops: [], assigned_requests: [] };

const render = async () => {
  const wrapper = mount(TripRequestAssignment, { props: { trip } });
  await flushPromises();
  return wrapper;
};

describe("trip request assignment async states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stub.resource.data = null;
    stub.resource.list.fetched = false;
    stub.resource.list.loading = false;
    reload.mockImplementation(async () => {
      stub.resource.list.fetched = true;
    });
  });

  it("shows the pending read as a skeleton instead of reporting no approved requests", async () => {
    reload.mockImplementation(() => new Promise(() => {}));
    stub.resource.list.loading = true;
    const wrapper = await render();

    expect(wrapper.get(".portal-skeleton").attributes("role")).toBe("status");
    expect(wrapper.text()).not.toContain(EMPTY_MESSAGE);
    wrapper.unmount();
  });

  it("reports a failed read as a failure, never as an empty result", async () => {
    reload.mockRejectedValue({ messages: ["تعذّر الوصول إلى الخادم."] });
    const wrapper = await render();

    expect(wrapper.get("[role='alert']").text()).toContain("تعذّر الوصول إلى الخادم.");
    expect(wrapper.text()).not.toContain(EMPTY_MESSAGE);
    expect(wrapper.find(".portal-skeleton").exists()).toBe(false);
    wrapper.unmount();
  });

  it("states there is nothing to assign only once a read has succeeded with no rows", async () => {
    reload.mockImplementation(async () => {
      stub.resource.data = [];
      stub.resource.list.fetched = true;
    });
    const wrapper = await render();

    expect(wrapper.text()).toContain(EMPTY_MESSAGE);
    expect(wrapper.find(".portal-skeleton").exists()).toBe(false);
    expect(wrapper.find("[role='alert']").exists()).toBe(false);
    wrapper.unmount();
  });

  it("lists the assignable requests once they arrive", async () => {
    reload.mockImplementation(async () => {
      stub.resource.data = [{ name: "TR-000012", from_location: "سكن الشمال", worker_count: 4 }];
      stub.resource.list.fetched = true;
    });
    const wrapper = await render();

    expect(wrapper.get(".record-reference").text()).toBe("TR-000012");
    expect(wrapper.text()).not.toContain(EMPTY_MESSAGE);
    wrapper.unmount();
  });

  it("names the empty selection beside the dead submit and drops it once a row is fully set", async () => {
    reload.mockImplementation(async () => {
      stub.resource.data = [{ name: "TR-000012", from_location: "سكن الشمال", worker_count: 4 }];
      stub.resource.list.fetched = true;
    });
    const wrapper = mount(TripRequestAssignment, {
      props: {
        trip: {
          ...trip,
          stops: [
            { stop_key: "S1", stop_name: "توقف الصعود" },
            { stop_key: "S2", stop_name: "توقف النزول" },
          ],
        },
      },
    });
    await flushPromises();
    const submit = wrapper.findAll("button").find((button) => button.text().includes("طلب"));

    expect(wrapper.get(".feature-reason").text()).toBe("اختر طلباً واحداً على الأقل.");
    expect(submit.attributes("disabled")).toBeDefined();

    await wrapper.get(".supervisor-request-assignment__choice input").setValue(true);
    const stops = wrapper.findAll(".supervisor-request-assignment__stops input");
    await stops[0].setValue("S1");
    await stops[1].setValue("S2");
    await flushPromises();

    expect(wrapper.find(".feature-reason").exists()).toBe(false);
    expect(submit.attributes("disabled")).toBeUndefined();
    wrapper.unmount();
  });
});
