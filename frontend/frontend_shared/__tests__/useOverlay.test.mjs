// Copyright (c) 2026, AFMCO and contributors
// The three rules an overlay must keep, asserted on real key events rather than on
// what the markup looks like: opening moves focus in, Tab cycles inside, Escape
// closes and hands focus back. Every assertion here started as an observed defect on
// /masar-supervisor (Tab walked onto eleven obscured background controls; Escape did
// nothing), so a regression must red this file before it reaches a supervisor.
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { defineComponent, h, ref } from "vue";
import { mount } from "@vue/test-utils";
import { useOverlay } from "@shared/useOverlay.js";

// A page with a background button (the "trigger") and an overlay holding two inputs.
const Host = defineComponent({
  setup() {
    const open = ref(false);
    const panel = ref(null);
    useOverlay({ active: open, container: panel, close: () => (open.value = false) });
    return { open, panel };
  },
  render() {
    return h("div", [
      h("button", { class: "outside-a", onClick: () => (this.open = true) }, "open"),
      h("button", { class: "outside-b" }, "background"),
      this.open
        ? h("div", { class: "panel", ref: "panel" }, [
            h("button", { class: "in-first" }, "first"),
            h("button", { class: "in-last" }, "last"),
          ])
        : null,
    ]);
  },
});

// jsdom reports offsetParent as null for everything, so the visibility filter must
// fall back to client rects; give every element a non-empty one.
const originalRects = Element.prototype.getClientRects;

beforeEach(() => {
  Element.prototype.getClientRects = () => [{ width: 10, height: 10 }];
});

afterEach(() => {
  Element.prototype.getClientRects = originalRects;
});

function key(name, shiftKey = false) {
  const e = new KeyboardEvent("keydown", { key: name, shiftKey, bubbles: true, cancelable: true });
  document.dispatchEvent(e);
  return e;
}

describe("useOverlay", () => {
  it("moves focus into the overlay when it opens", async () => {
    const w = mount(Host, { attachTo: document.body });
    w.find(".outside-a").element.focus();
    await w.find(".outside-a").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    expect(document.activeElement.className).toBe("in-first");
    w.unmount();
  });

  it("wraps Tab from the last item back to the first, never onto the page behind", async () => {
    const w = mount(Host, { attachTo: document.body });
    await w.find(".outside-a").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    w.find(".in-last").element.focus();
    const e = key("Tab");
    expect(e.defaultPrevented).toBe(true);
    expect(document.activeElement.className).toBe("in-first");
    w.unmount();
  });

  it("wraps Shift+Tab from the first item to the last", async () => {
    const w = mount(Host, { attachTo: document.body });
    await w.find(".outside-a").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    w.find(".in-first").element.focus();
    key("Tab", true);
    expect(document.activeElement.className).toBe("in-last");
    w.unmount();
  });

  // The defect this replaces: focus had escaped to a background control, and every
  // further Tab kept walking the page. Recovery must pull it back in.
  it("pulls focus back inside when it has escaped the overlay", async () => {
    const w = mount(Host, { attachTo: document.body });
    await w.find(".outside-a").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    w.find(".outside-b").element.focus();
    key("Tab");
    expect(document.activeElement.className).toBe("in-first");
    w.unmount();
  });

  it("closes on Escape and returns focus to the element that opened it", async () => {
    const w = mount(Host, { attachTo: document.body });
    w.find(".outside-a").element.focus();
    await w.find(".outside-a").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    expect(w.find(".panel").exists()).toBe(true);
    key("Escape");
    await w.vm.$nextTick();
    await new Promise((r) => setTimeout(r, 0));
    expect(w.find(".panel").exists()).toBe(false);
    expect(document.activeElement.className).toBe("outside-a");
    w.unmount();
  });

  it("ignores Escape and Tab while inactive", async () => {
    const w = mount(Host, { attachTo: document.body });
    w.find(".outside-b").element.focus();
    const e = key("Tab");
    expect(e.defaultPrevented).toBe(false);
    expect(document.activeElement.className).toBe("outside-b");
    w.unmount();
  });
});
