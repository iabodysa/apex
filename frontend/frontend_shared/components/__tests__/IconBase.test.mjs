// Copyright (c) 2026, AFMCO and contributors
// IconBase renders a geometry `shape` into the standard <svg> wrapper and applies
// the align + RTL-mirror classes exactly per prop — the safety net that lets every
// portal share one renderer without changing its icon box or direction behaviour.
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import IconBase from "@shared/components/IconBase.vue";

const shape = [
  { tag: "path", attrs: { d: "M4 4h16" } },
  { tag: "circle", attrs: { cx: "12", cy: "12", r: "4" } },
];

describe("IconBase", () => {
  it("renders each child element with its attributes", () => {
    const w = mount(IconBase, { props: { shape, name: "demo" } });
    expect(w.find("path").attributes("d")).toBe("M4 4h16");
    const c = w.find("circle");
    expect(c.attributes("cx")).toBe("12");
    expect(c.attributes("r")).toBe("4");
  });

  it("carries the standard svg wrapper attributes", () => {
    const w = mount(IconBase, { props: { shape, size: 30, strokeWidth: 3 } });
    const svg = w.find("svg");
    expect(svg.attributes("viewBox")).toBe("0 0 24 24");
    expect(svg.attributes("width")).toBe("30");
    expect(svg.attributes("stroke-width")).toBe("3");
    expect(svg.attributes("aria-hidden")).toBe("true");
  });

  it("applies the align class only when align=true", () => {
    expect(mount(IconBase, { props: { shape, align: true } }).find("svg").classes()).toContain("apex-icon");
    expect(mount(IconBase, { props: { shape, align: false } }).find("svg").classes()).not.toContain("apex-icon");
  });

  it("applies the mirror class only for a name in the mirror set", () => {
    const on = mount(IconBase, { props: { shape, name: "chevron", mirror: ["chevron"] } });
    expect(on.find("svg").classes()).toContain("apex-icon-mirror");
    const off = mount(IconBase, { props: { shape, name: "home", mirror: ["chevron"] } });
    expect(off.find("svg").classes()).not.toContain("apex-icon-mirror");
    const none = mount(IconBase, { props: { shape, name: "chevron", mirror: [] } });
    expect(none.find("svg").classes()).not.toContain("apex-icon-mirror");
  });

  it("renders an empty svg for an unknown (empty) shape", () => {
    const w = mount(IconBase, { props: { shape: [], name: "missing" } });
    expect(w.find("svg").exists()).toBe(true);
    expect(w.find("path").exists()).toBe(false);
  });
});
