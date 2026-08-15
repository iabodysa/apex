import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { selectBuilding } from "./building.js";

// A greyed control on a housing screen is a dead end unless it names the step still missing: the
// supervisor is standing in a corridor with a phone, not reading the disabled expression. Each of
// these mounts the screen in the state that greys the control and reads the sentence back.
const resources = vi.hoisted(() => ({ rooms: null, delivery: null, grid: null }));
const route = vi.hoisted(() => ({ params: { name: "FAD-0001" }, query: {} }));

vi.mock("frappe-ui", async () => {
  const { reactive } = await import("vue");
  resources.rooms = reactive({
    data: [],
    list: { loading: false },
    start: 0,
    pageLength: 100,
    hasNextPage: false,
    update: () => {},
    reload: vi.fn(async () => {}),
    insert: { loading: false, submit: vi.fn() },
  });
  resources.delivery = reactive({
    doc: null,
    get: { loading: false, error: null },
    reload: vi.fn(),
  });
  resources.grid = reactive({ data: null, loading: false, error: null, fetch: vi.fn() });
  return {
    Badge: { props: ["label"], template: "<span>{{ label }}</span>" },
    Button: {
      props: ["disabled", "type"],
      template: '<button :type="type || \'button\'" :disabled="disabled"><slot /></button>',
    },
    ErrorMessage: { props: ["message"], template: "<p role='alert'>{{ message }}</p>" },
    FormControl: {
      props: ["modelValue", "label", "type", "options", "description"],
      emits: ["update:modelValue"],
      template: "<label>{{ label }}<input :value='modelValue' :aria-label='label' @input=\"$emit('update:modelValue', $event.target.value)\" /></label>",
    },
    createDocumentResource: () => resources.delivery,
    createListResource: () => resources.rooms,
    createResource: ({ url }) => (url.endsWith("get_building_grid")
      ? resources.grid
      : { loading: false, data: null, fetch: vi.fn(), submit: vi.fn() }),
    toast: { create: vi.fn() },
  };
});

vi.mock("vue-router", async () => {
  const actual = await vi.importActual("vue-router");
  return { ...actual, useRoute: () => route };
});

import MaintenanceRequestCreatePage from "./pages/MaintenanceRequestCreatePage.vue";
import DeliveryDetailPage from "./pages/DeliveryDetailPage.vue";
import BedsPage from "./pages/BedsPage.vue";

const stubs = { BuildingPicker: true, PortalSkeleton: true, RouterLink: true };

beforeEach(() => {
  selectBuilding("");
  resources.rooms.data = [];
  resources.rooms.list.loading = false;
  resources.delivery.doc = null;
  resources.grid.data = null;
  route.query = {};
});

afterEach(() => {
  selectBuilding("");
  globalThis.window.apex_portal = undefined;
});

describe("a greyed housing control names the step still missing", () => {
  it("walks the maintenance request through its four blockers one sentence at a time", async () => {
    resources.rooms.data = [{ name: "ROOM-1", room_number: "A-101" }];
    const wrapper = mount(MaintenanceRequestCreatePage, { global: { stubs } });
    const submit = () => wrapper.get('button[type="submit"]');

    expect(wrapper.text()).toContain("اختر المبنى أولاً.");
    expect(submit().attributes()).toHaveProperty("disabled");

    selectBuilding("BLD-1");
    await nextTick();
    await nextTick();
    expect(wrapper.text()).toContain("اختر الغرفة.");

    await wrapper.get('[aria-label="الغرفة"]').setValue("ROOM-1");
    expect(wrapper.text()).toContain("اكتب وصف المشكلة.");
    expect(submit().attributes()).toHaveProperty("disabled");

    await wrapper.get('[aria-label="وصف المشكلة"]').setValue("تسريب في الحمام");
    expect(wrapper.text()).not.toContain("اكتب وصف المشكلة.");
    expect(submit().attributes().disabled).toBeUndefined();
    wrapper.unmount();
  });

  it("says the room list is still loading rather than greying the submit in silence", async () => {
    selectBuilding("BLD-1");
    resources.rooms.list.loading = true;
    const wrapper = mount(MaintenanceRequestCreatePage, { global: { stubs } });

    expect(wrapper.text()).toContain("جارٍ تحميل غرف المبنى.");
    expect(wrapper.get('button[type="submit"]').attributes()).toHaveProperty("disabled");
    wrapper.unmount();
  });

  it("separates an already-passed delivery gate from a call still in flight", async () => {
    globalThis.window.apex_portal = { capabilities: ["clear_exit_1", "clear_exit_3"] };
    resources.delivery.doc = {
      name: "FAD-0001",
      status: "Released",
      exit1_security_cleared: 1,
      exit3_receiving_cleared: 0,
    };
    const wrapper = mount(DeliveryDetailPage, { global: { stubs } });

    expect(wrapper.text()).toContain("اعتُمدت بوابة التسليم مسبقاً.");
    expect(wrapper.text()).not.toContain("اعتُمد الاستلام مسبقاً.");
    wrapper.unmount();
  });

  // The assignment flow invites a tap on a bed. An occupant's name says who is there; it does not
  // say the tile has stopped accepting the tap, and only the occupied tile is inert.
  it("tells the assignment flow which bed refuses the tap, not merely who is in it", async () => {
    route.query = { party_type: "Employee", party: "HR-EMP-1", label: "أحمد" };
    resources.grid.data = {
      floors: [{
        floor_label: "1",
        rooms: [{
          room: "ROOM-1",
          room_number: "A-101",
          readiness_status: "Ready",
          beds: [
            { bed: "BED-1", bed_code: "A-101-1", occupant: { employee_name: "سالم" } },
            { bed: "BED-2", bed_code: "A-101-2" },
          ],
        }],
      }],
    };
    selectBuilding("BLD-1");
    const wrapper = mount(BedsPage, { global: { stubs } });
    await nextTick();

    const tiles = wrapper.findAll(".bed-grid > *");
    expect(tiles[0].attributes("aria-disabled")).toBe("true");
    expect(tiles[0].text()).toContain("مشغول، لا يقبل إسناداً");
    expect(tiles[1].attributes("aria-disabled")).toBeUndefined();
    expect(tiles[1].text()).not.toContain("مشغول، لا يقبل إسناداً");
    wrapper.unmount();
  });
});
