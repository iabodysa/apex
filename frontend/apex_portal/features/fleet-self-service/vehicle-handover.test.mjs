import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const { checklistFetch, handoverSubmit } = vi.hoisted(() => ({
  checklistFetch: vi.fn(),
  handoverSubmit: vi.fn(),
}));

vi.mock("frappe-ui", () => ({
  Button: {
    props: ["type", "disabled"],
    template: '<button :type="type || \'button\'" :disabled="disabled"><slot /></button>',
  },
  FormControl: {
    props: ["modelValue", "type", "label"],
    emits: ["update:modelValue"],
    template: '<label>{{ label }}<input :type="type === \'number\' ? \'number\' : \'text\'" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" /></label>',
  },
  FileUploader: {
    emits: ["success"],
    template: '<div><button class="test-upload" type="button" @click="$emit(\'success\', { file_url: \'/private/files/signed.pdf\' })">upload</button><slot :open-file-selector="() => {}" :uploading="false" :error="null" /></div>',
  },
  createResource: vi.fn(({ url }) => ({
    loading: false,
    fetch: url.endsWith("get_handover_checklist") ? checklistFetch : vi.fn(),
    submit: url.endsWith("receive_vehicle") || url.endsWith("return_vehicle")
      ? handoverSubmit
      : vi.fn(),
  })),
}));

import VehicleHandoverForm from "./components/VehicleHandoverForm.vue";

describe("vehicle handover form", () => {
  beforeEach(() => {
    checklistFetch.mockReset();
    handoverSubmit.mockReset();
  });

  it("submits every decision, failed remark, template, and evidence only once", async () => {
    checklistFetch.mockResolvedValue({
      direction: "Receipt",
      vehicle: "VEH-1",
      assignment: "VA-0001",
      template: "VHC-1",
      items: [
        { check_item: "الإطارات", default_remark: "" },
        { check_item: "المصابيح", default_remark: "صف العطل" },
      ],
    });
    let finish;
    handoverSubmit.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const wrapper = mount(VehicleHandoverForm, {
      props: {
        direction: "Receipt",
        title: "استلام المركبة",
        intro: "افحص المركبة",
      },
    });
    await flushPromises();

    const items = wrapper.findAll(".vehicle-handover__item");
    await items[0].findAll("button")[0].trigger("click");
    await items[1].findAll("button")[1].trigger("click");
    await items[1].get("input").setValue("المصباح الأيسر لا يعمل");
    await wrapper.get('input[type="number"]').setValue("12345");
    await wrapper.get(".test-upload").trigger("click");
    await wrapper.get("form").trigger("submit");
    await wrapper.get("form").trigger("submit");

    expect(handoverSubmit).toHaveBeenCalledOnce();
    expect(handoverSubmit).toHaveBeenCalledWith(expect.objectContaining({
      assignment: "VA-0001",
      odometer: 12345,
      signed_evidence: "/private/files/signed.pdf",
      checklist_template: "VHC-1",
      inspection_rows: JSON.stringify([
        { check_item: "الإطارات", ok: 1, remark: "" },
        { check_item: "المصابيح", ok: 0, remark: "المصباح الأيسر لا يعمل" },
      ]),
    }));
    finish({ name: "VH-1", status: "Submitted" });
    await flushPromises();
    expect(wrapper.text()).toContain("تم تسجيل استلام المركبة");
    expect(wrapper.get('button[type="submit"]').attributes()).toHaveProperty("disabled");
  });

  it("fails closed with actionable help when no native template exists", async () => {
    checklistFetch.mockRejectedValue({
      _server_messages: JSON.stringify([
        JSON.stringify({ message: "لا يوجد قالب فحص مركبة نشط." }),
      ]),
    });
    const wrapper = mount(VehicleHandoverForm, {
      props: {
        direction: "Return",
        title: "إرجاع المركبة",
        intro: "افحص المركبة",
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("لا يوجد قالب فحص مركبة نشط.");
    expect(wrapper.find("form").exists()).toBe(false);
    expect(handoverSubmit).not.toHaveBeenCalled();
  });
});
