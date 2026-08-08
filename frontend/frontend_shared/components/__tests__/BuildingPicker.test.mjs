// Copyright (c) 2026, AFMCO and contributors
// The shared BuildingPicker (housing/safety) lists the buildings a user may read
// and emits `select`. Only createListResource is replaced — the rest of frappe-ui
// stays real, so the test drives the list-render + click path and the
// single-building auto-select without a bench.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import BuildingPicker from "@shared/components/BuildingPicker.vue";

const rows = vi.hoisted(() => ({ current: [] }));

vi.mock("frappe-ui", async (importOriginal) => ({
  ...(await importOriginal()),
  createListResource(opts) {
    if (opts && typeof opts.onSuccess === "function") opts.onSuccess(rows.current);
    return { data: rows.current, list: { loading: false } };
  },
}));

const __setRows = (next) => {
  rows.current = next;
};

describe("BuildingPicker (shared)", () => {
  beforeEach(() => __setRows([]));

  it("renders a row per building and emits select on click", async () => {
    __setRows([
      { name: "B-1", building_name: "Tower A" },
      { name: "B-2", building_name: "Tower B" },
    ]);
    const w = mount(BuildingPicker);
    await flushPromises();
    const items = w.findAll(".b-item");
    expect(items.length).toBe(2);
    await items[1].trigger("click");
    expect(w.emitted("select")[0]).toEqual(["B-2", "Tower B"]);
  });

  it("auto-selects when the user is scoped to exactly one building", async () => {
    __setRows([{ name: "B-9", building_name: "Only House" }]);
    const w = mount(BuildingPicker);
    await flushPromises();
    expect(w.emitted("select")).toBeTruthy();
    expect(w.emitted("select")[0]).toEqual(["B-9", "Only House"]);
  });

  it("shows the empty state when no building is readable", async () => {
    __setRows([]);
    const w = mount(BuildingPicker);
    await flushPromises();
    expect(w.find(".picker-empty").exists()).toBe(true);
    expect(w.findAll(".b-item").length).toBe(0);
  });
});
