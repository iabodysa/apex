import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import PortalErrorState from "./PortalErrorState.vue";
import { safeErrorMessage } from "../core/errorMessage.js";

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

  it("extracts actionable Frappe server messages without exposing internal traces", () => {
    const error = {
      message: "Traceback (most recent call last): File \"/home/frappe/apps/apex/api.py\", line 42",
      _server_messages: JSON.stringify([
        JSON.stringify({ message: "لا يوجد قالب فحص نشط للاستلام." }),
      ]),
      exc: "pymysql.err.ProgrammingError: SELECT secret FROM tabUser",
    };

    expect(safeErrorMessage(error, "تعذّر تنفيذ الإجراء.")).toBe(
      "لا يوجد قالب فحص نشط للاستلام.",
    );
    expect(safeErrorMessage({ message: error.message }, "تعذّر تنفيذ الإجراء.")).toBe(
      "تعذّر تنفيذ الإجراء.",
    );
  });
});
