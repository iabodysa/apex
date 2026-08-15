import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import ArrivalRegistrationForm from "./ArrivalRegistrationForm.vue";

const { resource } = vi.hoisted(() => ({
  resource: { loading: false, submit: vi.fn() },
}));

vi.mock("frappe-ui", () => ({
  Button: { template: "<button><slot /></button>" },
  FormControl: {
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: "<input :value='modelValue' :aria-label='label' @input=\"$emit('update:modelValue', $event.target.value)\" />",
  },
  createResource: () => resource,
}));

const manifestRow = Object.freeze({
  row: "ROW-1",
  worker_name: "سعيد",
  passport_number: "P-1",
  nationality: "هندي",
  project: "PROJ-1",
  labour_supplier: "SUP-1",
});

describe("ArrivalRegistrationForm", () => {
  beforeEach(() => {
    resource.loading = false;
    resource.submit.mockReset().mockResolvedValue({ label: "سعيد", party: "TW-1" });
  });

  it("seeds the identity the manifest carries and leaves the rest to the clerk", async () => {
    const wrapper = mount(ArrivalRegistrationForm, {
      props: { manifest: null, building: "BLD-1" },
    });
    expect(wrapper.get('[aria-label="اسم العامل"]').element.value).toBe("");

    await wrapper.setProps({ manifest: manifestRow });

    expect(wrapper.get('[aria-label="اسم العامل"]').element.value).toBe("سعيد");
    expect(wrapper.get('[aria-label="رقم الجواز"]').element.value).toBe("P-1");
    expect(wrapper.get('[aria-label="الجنسية"]').element.value).toBe("هندي");
    // The batch never carries a phone, so the one field the clerk fills is never overwritten.
    await wrapper.get('[aria-label="رقم الجوال"]').setValue("0500000000");
    await wrapper.setProps({ manifest: null });

    expect(wrapper.get('[aria-label="اسم العامل"]').element.value).toBe("سعيد");
    expect(wrapper.get('[aria-label="رقم الجوال"]').element.value).toBe("0500000000");
    wrapper.unmount();
  });

  it("registers the typed worker against the picked batch row, then clears the form", async () => {
    const wrapper = mount(ArrivalRegistrationForm, {
      props: { manifest: manifestRow, building: "BLD-1" },
    });
    await wrapper.get('[aria-label="رقم الجوال"]').setValue("0500000000");

    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(resource.submit).toHaveBeenCalledWith(expect.objectContaining({
      worker_name: "سعيد",
      passport_number: "P-1",
      nationality: "هندي",
      cell_number: "0500000000",
      building: "BLD-1",
      batch_row: "ROW-1",
      project: "PROJ-1",
    }));
    expect(wrapper.emitted("registered")).toEqual([[{ label: "سعيد", party: "TW-1" }]]);
    expect(wrapper.get('[aria-label="اسم العامل"]').element.value).toBe("");
    wrapper.unmount();
  });

  it("names the field holding the registration, and stops naming it once supplied", async () => {
    const wrapper = mount(ArrivalRegistrationForm, {
      props: { manifest: null, building: "BLD-1" },
    });
    expect(wrapper.text()).toContain("اكتب اسم العامل لتفعيل التسجيل.");

    await wrapper.get('[aria-label="اسم العامل"]').setValue("سعيد");
    expect(wrapper.text()).toContain("اكتب رقم الجواز لتفعيل التسجيل.");

    await wrapper.get('[aria-label="رقم الجواز"]').setValue("P-9");
    expect(wrapper.text()).not.toContain("لتفعيل التسجيل");
    wrapper.unmount();
  });
});
