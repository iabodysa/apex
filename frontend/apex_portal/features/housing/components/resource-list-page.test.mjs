import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createResource } from "frappe-ui";
import ResourceListPage from "./ResourceListPage.vue";

vi.mock("frappe-ui", () => ({
  Button: {
    props: ["label"],
    template: "<button>{{ label }}</button>",
  },
  ErrorMessage: { template: "<p />" },
  LoadingIndicator: { template: "<span />" },
  createResource: vi.fn(() => ({
    data: [],
    loading: false,
    error: null,
    fetch: vi.fn(),
  })),
}));

describe("ResourceListPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("gives the refresh action a visible label", () => {
    const refresh = vi.fn();
    const wrapper = mount(ResourceListPage, {
      props: {
        title: "نظرة عامة",
        rows: [],
        loading: false,
        error: null,
        refresh,
      },
    });

    expect(wrapper.get("button").text()).toBe("تحديث");
    expect(createResource).not.toHaveBeenCalled();
  });

  it("shows a human title first and keeps the serial as a secondary reference", () => {
    const wrapper = mount(ResourceListPage, {
      props: {
        title: "طلبات الصيانة",
        titleFields: ["issue_type"],
        fallbackTitle: "طلب صيانة",
        rows: [{ name: "MR-2026-00042", issue_type: "تكييف", status: "Open" }],
        refresh: vi.fn(),
      },
    });

    expect(wrapper.get("strong").text()).toBe("تكييف");
    expect(wrapper.get("bdi").text()).toBe("MR-2026-00042");
  });
});
