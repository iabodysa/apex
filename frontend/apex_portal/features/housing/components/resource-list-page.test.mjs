import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import ResourceListPage from "./ResourceListPage.vue";

vi.mock("frappe-ui", () => ({
  Button: {
    props: ["label"],
    template: '<button>{{ label }}</button>',
  },
  ErrorMessage: { template: "<p />" },
  LoadingIndicator: { template: "<span />" },
  createResource: () => ({ data: [], loading: false, error: null, fetch: vi.fn() }),
}));

describe("ResourceListPage", () => {
  it("gives the refresh action a visible label", () => {
    const wrapper = mount(ResourceListPage, {
      props: { title: "نظرة عامة", endpoint: "apex.test.list" },
    });

    expect(wrapper.get("button").text()).toBe("تحديث");
  });
});
