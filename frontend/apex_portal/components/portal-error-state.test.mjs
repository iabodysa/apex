import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import PortalErrorState from "./PortalErrorState.vue";
import { errorStatus, safeErrorMessage } from "../core/errorMessage.js";

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

  it("normalizes frappe-ui response status and hides retry for permission failures", () => {
    const error = {
      message: 'Traceback: File "/home/frappe/apps/apex/secret.py", line 9',
      response: {
        status: 403,
        data: {
          _server_messages: JSON.stringify([
            JSON.stringify({ message: "لا تملك صلاحية عرض هذا السجل." }),
          ]),
        },
      },
    };
    const wrapper = mount(PortalErrorState, { props: { message: error } });

    expect(errorStatus(error)).toBe(403);
    expect(wrapper.text()).toContain("لا تملك صلاحية عرض هذا السجل.");
    expect(wrapper.text()).not.toContain("Traceback");
    expect(wrapper.find("button").exists()).toBe(false);
  });

  it("prefers frappe-ui messages and never falls back to its composed endpoint line", () => {
    const composed = new Error("/api/method/apex.salis.api.masar.list_worker_requests ValidationError");
    composed.response = { status: 500 };
    composed.messages = ["تعذّر الوصول إلى الخادم."];

    expect(safeErrorMessage(composed, "تحقق من الاتصال.")).toBe("تعذّر الوصول إلى الخادم.");

    const silent = new Error("/api/method/apex.salis.api.masar.list_worker_requests ValidationError");
    silent.response = { status: 403 };
    silent.messages = [];

    expect(errorStatus(silent)).toBe(403);
    expect(safeErrorMessage(silent, "لا تملك صلاحية عرض هذه الصفحة.")).toBe(
      "لا تملك صلاحية عرض هذه الصفحة.",
    );
  });
});
