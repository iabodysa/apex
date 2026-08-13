import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const { tripsReload, tripRecordFetch, createAdHocSubmit, assignSubmit } = vi.hoisted(() => ({
  tripsReload: vi.fn().mockResolvedValue(undefined),
  tripRecordFetch: vi.fn().mockResolvedValue({ stops: [] }),
  createAdHocSubmit: vi.fn().mockResolvedValue({ name: "TRIP-1" }),
  assignSubmit: vi.fn().mockResolvedValue({ name: "TRIP-1" }),
}));

vi.mock("frappe-ui", () => ({
  Button: {
    props: ["type", "disabled"],
    template: '<button :type="type || \'button\'" :disabled="disabled"><slot /></button>',
  },
  FormControl: {
    props: ["modelValue", "label", "options"],
    emits: ["update:modelValue"],
    template: '<label>{{ label }}<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" /><output>{{ (options || []).map((item) => item.label).join("|") }}</output></label>',
  },
  createListResource: vi.fn(() => ({
    data: [],
    list: { loading: false, error: null },
    hasNextPage: false,
    reload: tripsReload,
    next: vi.fn(),
  })),
  createResource: vi.fn(({ url }) => ({
    data: null,
    loading: false,
    fetch: url === "frappe.client.get" ? tripRecordFetch : vi.fn().mockResolvedValue({ stops: [] }),
    submit: url.endsWith("create_ad_hoc_trip") ? createAdHocSubmit : assignSubmit,
  })),
}));

import RequestTripPlanning from "./components/RequestTripPlanning.vue";

const approvedRequest = {
  name: "REQ-9",
  status: "Approved",
  project: "PROJ-1",
  accommodation_building: "BLD-1",
  from_location: "سكن الشمال",
  to_location: "مشروع المطار",
  pickup_datetime: "2026-08-15 06:00:00",
};

describe("request trip planning", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    tripRecordFetch.mockResolvedValue({ stops: [] });
  });

  it("creates the ad-hoc trip and its request assignment in one server call", async () => {
    const wrapper = mount(RequestTripPlanning, { props: { request: approvedRequest } });
    await flushPromises();
    const adHocForm = wrapper.findAll("form")[1];
    const end = adHocForm.findAll("label").find((label) => label.text().includes("وقت النهاية"));
    await end.get("input").setValue("2026-08-15 07:00:00");
    await adHocForm.trigger("submit");
    await flushPromises();

    expect(createAdHocSubmit).toHaveBeenCalledOnce();
    const call = createAdHocSubmit.mock.calls[0][0];
    expect(JSON.parse(call.trip)).toMatchObject({
      project: "PROJ-1",
      trip_date: "2026-08-15",
      stops: [
        expect.objectContaining({ stop_key: "pickup", stop_name: "سكن الشمال" }),
        expect.objectContaining({ stop_key: "dropoff", stop_name: "مشروع المطار" }),
      ],
    });
    expect(JSON.parse(call.transport_requests)).toEqual([
      { transport_request: "REQ-9", pickup_stop: "pickup", dropoff_stop: "dropoff" },
    ]);
  });

  it("does not offer a non-atomic assignment while the request is only validated", async () => {
    const wrapper = mount(RequestTripPlanning, {
      props: { request: { ...approvedRequest, status: "Validated" } },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("اعتمد الطلب أولاً");
    expect(wrapper.find("form").exists()).toBe(false);
    expect(tripsReload).not.toHaveBeenCalled();
    expect(createAdHocSubmit).not.toHaveBeenCalled();
    expect(assignSubmit).not.toHaveBeenCalled();
  });

  it("loads planned trips when workflow approval updates the existing detail component", async () => {
    const wrapper = mount(RequestTripPlanning, {
      props: { request: { ...approvedRequest, status: "Validated" } },
    });
    await flushPromises();
    expect(tripsReload).not.toHaveBeenCalled();

    await wrapper.setProps({ request: { ...approvedRequest, status: "Approved" } });
    await flushPromises();

    expect(tripsReload).toHaveBeenCalledOnce();
    expect(wrapper.findAll("form")).toHaveLength(2);
  });

  it("keeps the selected trip stops when an older trip response arrives late", async () => {
    const pending = new Map();
    tripRecordFetch.mockImplementation(({ name }) => new Promise((resolve) => pending.set(name, resolve)));
    const wrapper = mount(RequestTripPlanning, { props: { request: approvedRequest } });
    await flushPromises();
    const tripInput = wrapper.findAll("form")[0].findAll("input")[0];

    await tripInput.setValue("TRIP-A");
    await tripInput.setValue("TRIP-B");
    pending.get("TRIP-B")({ stops: [{ stop_key: "B", stop_name: "توقف ب" }] });
    await flushPromises();
    pending.get("TRIP-A")({ stops: [{ stop_key: "A", stop_name: "توقف أ" }] });
    await flushPromises();

    expect(wrapper.text()).toContain("توقف ب");
    expect(wrapper.text()).not.toContain("توقف أ");
  });

  it("keeps the newest stops of a re-selected trip when its own earlier response arrives last", async () => {
    const pending = [];
    tripRecordFetch.mockImplementation(() => new Promise((resolve) => pending.push(resolve)));
    const wrapper = mount(RequestTripPlanning, { props: { request: approvedRequest } });
    await flushPromises();
    const tripInput = wrapper.findAll("form")[0].findAll("input")[0];

    await tripInput.setValue("TRIP-A");
    await tripInput.setValue("TRIP-B");
    await tripInput.setValue("TRIP-A");
    expect(pending).toHaveLength(3);

    pending[2]({ stops: [{ stop_key: "A2", stop_name: "توقف أ الحالي" }] });
    await flushPromises();
    pending[1]({ stops: [{ stop_key: "B", stop_name: "توقف ب" }] });
    pending[0]({ stops: [{ stop_key: "A1", stop_name: "توقف أ القديم" }] });
    await flushPromises();

    expect(wrapper.text()).toContain("توقف أ الحالي");
    expect(wrapper.text()).not.toContain("توقف أ القديم");
    expect(wrapper.text()).not.toContain("توقف ب");
  });
});
