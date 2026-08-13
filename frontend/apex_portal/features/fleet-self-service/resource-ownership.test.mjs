import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createResource } from "frappe-ui";
import AdditionalFuelRequestPage from "./pages/AdditionalFuelRequestPage.vue";

vi.mock("frappe-ui", () => ({
  Button: { template: "<button><slot /></button>" },
  FileUploader: { template: "<div><slot /></div>" },
  FormControl: { template: "<input />" },
  createResource: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    submit: vi.fn().mockResolvedValue(null),
  })),
}));

describe("Salis representative resource ownership", () => {
  it("creates only the page-local additional fuel resource", () => {
    mount(AdditionalFuelRequestPage);

    expect(createResource).toHaveBeenCalledOnce();
    expect(createResource).toHaveBeenCalledWith({
      url: "apex.salis.api.fleet_employee.submit_additional_fuel_request",
      method: "POST",
      auto: false,
    });
  });
});
