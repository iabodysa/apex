import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import PortalSkeleton from "./PortalSkeleton.vue";

describe("shared portal skeleton", () => {
  it("announces one localized status while exposing the incoming record shape", () => {
    const wrapper = mount(PortalSkeleton, { props: { rows: 3, label: "جارٍ تحميل الرحلات" } });

    expect(wrapper.attributes("role")).toBe("status");
    expect(wrapper.attributes("aria-label")).toBe("جارٍ تحميل الرحلات");
    expect(wrapper.findAll(".portal-skeleton__row")).toHaveLength(3);
    expect(wrapper.find(".portal-skeleton__visual").attributes("aria-hidden")).toBe("true");
  });
});
