import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createDocumentResource, createListResource } from "frappe-ui";
import DeliveryListPage from "./pages/DeliveryListPage.vue";
import MaintenanceRequestDetailPage from "./pages/MaintenanceRequestDetailPage.vue";

vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { name: "MR-0001" } }),
}));

vi.mock("frappe-ui", () => ({
  createDocumentResource: vi.fn(() => ({
    doc: null,
    get: { loading: false, error: null },
    reload: vi.fn(),
  })),
  createListResource: vi.fn(() => ({
    data: [],
    list: { loading: false, error: null },
    fetch: vi.fn(),
  })),
}));

const ResourceListPage = {
  props: ["rows", "loading", "error", "refresh"],
  template: "<section />",
};

describe("housing native DocType resources", () => {
  beforeEach(() => vi.clearAllMocks());

  it("uses createListResource for an ordinary DocType list", () => {
    mount(DeliveryListPage, { global: { stubs: { ResourceListPage } } });

    expect(createListResource).toHaveBeenCalledWith({
      doctype: "Facility Asset Delivery",
      fields: [
        "name", "status", "facility_asset", "facility_asset.asset_name as asset_name",
        "asset_serial_number", "from_building", "to_building", "delivery_date",
      ],
      orderBy: "modified desc",
      pageLength: 50,
      auto: true,
    });
  });

  it("uses createDocumentResource for an ordinary DocType record", () => {
    mount(MaintenanceRequestDetailPage, {
      global: { stubs: { ResourceListPage } },
    });

    expect(createDocumentResource).toHaveBeenCalledWith({
      doctype: "Maintenance Request",
      name: "MR-0001",
    });
  });

  it("keeps project selection permission-aware and session resources uncached", () => {
    const root = join(process.cwd(), "features/housing");
    const bed = readFileSync(join(root, "pages/BedDetailPage.vue"), "utf8");
    const buildings = readFileSync(join(root, "data/buildings.js"), "utf8");
    const maintenance = readFileSync(join(root, "pages/MaintenanceRequestCreatePage.vue"), "utf8");

    expect(bed).toContain('doctype: "Project"');
    expect(bed).toContain('v-model="checkInForm.project"');
    expect(bed).toContain('!checkInForm.project');
    expect(buildings).not.toContain("cache:");
    expect(maintenance).toContain("await rooms.reload()");
  });

  it("does not offer a second bed assignment to an already housed arrival", () => {
    const arrivals = readFileSync(
      join(process.cwd(), "features/housing/pages/ArrivalsPage.vue"),
      "utf8",
    );

    expect(arrivals).toContain("row.housed ? 'تم تسكينه'");
    expect(arrivals).toContain('v-if="row.arrived && !row.housed"');
  });
});
