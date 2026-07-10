// Copyright (c) 2026, AFMCO and contributors
// The shared BuildingPicker (housing/safety) lists the buildings a user may read
// and emits `select`. frappe-ui is aliased to a fixture stub (see vitest.config) so
// the test drives the list-render + click path and the single-building auto-select
// without a bench.
import { describe, it, expect, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { __setRows } from "frappe-ui";
import BuildingPicker from "@shared/components/BuildingPicker.vue";

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
