import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("frappe-ui", () => ({
  Button: {
    props: ["disabled"],
    template: '<button :disabled="disabled"><slot /></button>',
  },
  ErrorMessage: { props: ["message"], template: "<p role='alert'>{{ message }}</p>" },
  FormControl: {
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: "<input :value='modelValue' :aria-label='label' @input=\"$emit('update:modelValue', $event.target.value)\" />",
  },
  createResource: () => ({ loading: false, submit: vi.fn() }),
  toast: { create: vi.fn() },
}));

vi.mock("frappe-ui/frappe", () => ({
  Link: {
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: "<input :value='modelValue' :aria-label='label' @input=\"$emit('update:modelValue', $event.target.value)\" />",
  },
}));

import TransferPage from "./pages/TransferPage.vue";

describe("occupant transfer", () => {
  it("says which bed is still unpicked while the transfer stays disabled", async () => {
    const wrapper = mount(TransferPage);
    const submit = wrapper.get('button[type="submit"]');

    expect(submit.attributes()).toHaveProperty("disabled");
    expect(wrapper.text()).toContain("اختر السرير الحالي لتفعيل النقل.");

    await wrapper.get('[aria-label="السرير الحالي"]').setValue("A101-B01");
    expect(wrapper.text()).toContain("اختر السرير الجديد لتفعيل النقل.");
    expect(submit.attributes()).toHaveProperty("disabled");

    await wrapper.get('[aria-label="السرير الجديد"]').setValue("A102-B03");
    expect(wrapper.text()).not.toContain("لتفعيل النقل");
    expect(submit.attributes().disabled).toBeUndefined();
    wrapper.unmount();
  });
});
