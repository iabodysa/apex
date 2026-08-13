import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import PortalErrorState from "./PortalErrorState.vue";

describe("shared portal error state", () => {
  it("sanitizes backend detail and never repeats the title as its explanation", async () => {
    const wrapper = mount(PortalErrorState, {
      props: {
        title: "تعذّر تحميل البيانات",
        message: "<strong>تعذّر تحميل البيانات</strong>",
      },
    });

    expect(wrapper.get("h2").text()).toBe("تعذّر تحميل البيانات");
    expect(wrapper.get("p").text()).toBe("تحقق من الاتصال ثم حاول مرة أخرى.");
    expect(wrapper.html()).not.toContain("<strong>");
    await wrapper.get("button").trigger("click");
    expect(wrapper.emitted("retry")).toHaveLength(1);
  });
});
