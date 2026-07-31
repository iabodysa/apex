// Copyright (c) 2026, AFMCO and contributors
//
// Runtime proof that the /fleet employee nav's active state FOLLOWS THE READER.
//
// The source guard (apex/www/test_fleet_employee_nav.py) can only say that the
// markup binds `is-active` to state and that the file mentions an
// IntersectionObserver. Both sentences stay true of a spy that never fires and of
// a highlight that marks two items at once, which is why the behaviour itself is
// asserted here instead: reaching a section marks ITS item and unmarks every
// other one.
//
// jsdom ships no IntersectionObserver, and the page bails out of installing the
// spy when the constructor is missing (`typeof IntersectionObserver ===
// "undefined"`). The stub below is therefore not decoration — it is the thing
// that puts the spy under test at all, and it doubles as the scroll position: a
// callback carrying "these sections are in the detector band" IS the reader
// having scrolled there.
//
// It lives in the shared harness because that is the one frontend suite CI runs
// (`npm test -w frontend_shared`, Portal Tests / shared-components); fleet ships
// a bundle, not a test runner.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";

// The page's only real boundary: the identity-scoped fleet_employee endpoints.
// Stubbed so the mount needs no bench. The three <section>s render whatever the
// data layer answers, so the nav is fully exercised on an empty account.
vi.mock("@shared/call", () => ({
  configureApi: () => {},
  call: vi.fn(async () => null),
}));

import App from "../../../fleet/src/App.vue";

let observers = [];

class ObserverStub {
  constructor(cb, options) {
    this.cb = cb;
    this.options = options;
    this.targets = [];
    this.live = true;
    observers.push(this);
  }
  observe(el) {
    this.targets.push(el);
  }
  unobserve(el) {
    this.targets = this.targets.filter((t) => t !== el);
  }
  disconnect() {
    this.live = false;
    this.targets = [];
  }
}

const spy = () => observers[observers.length - 1];
const links = (w) => w.findAll(".fleet-nav a");
const hrefs = (w) => links(w).map((a) => a.attributes("href"));
const marked = (w) =>
  links(w)
    .filter((a) => a.classes("is-active"))
    .map((a) => a.attributes("href"));
const announced = (w) =>
  links(w)
    .filter((a) => a.attributes("aria-current") === "location")
    .map((a) => a.attributes("href"));

/** Put the reader at `ids`: one observer callback naming what is in the band. */
async function reach(...ids) {
  const o = spy();
  o.cb(o.targets.map((el) => ({ target: el, isIntersecting: ids.includes(el.id) })));
  await nextTick();
}

/** Drain the macrotask queue too — jsdom defers hashchange past a microtask. */
async function settle() {
  await new Promise((r) => setTimeout(r, 0));
  await nextTick();
}

describe("/fleet employee nav", () => {
  let w = null;

  beforeEach(() => {
    observers = [];
    globalThis.IntersectionObserver = ObserverStub;
    // A fragment left by a previous test's click would deep-link the next mount.
    window.history.replaceState(null, "", "/");
  });

  afterEach(() => {
    if (w) w.unmount();
    w = null;
    delete globalThis.IntersectionObserver;
  });

  // attachTo is load-bearing, not tidiness: the page resolves its sections with
  // document.getElementById, which finds nothing in a detached wrapper, and the
  // spy is then never installed. A "passing" test on a detached mount would be
  // asserting the bail-out branch.
  const open = () => mount(App, { attachTo: document.body });

  it("watches exactly the sections the nav offers", () => {
    w = open();
    expect(hrefs(w)).toEqual(["#vehicle", "#trips", "#fuel"]);
    expect(spy().targets.map((el) => el.id)).toEqual(["vehicle", "trips", "fuel"]);
    // The band starts BELOW the sticky header and ends before the fold, so
    // "current" means "at the top of what is being read". A zero rootMargin
    // would let the last section on screen own the highlight.
    expect(spy().options.rootMargin).toMatch(/^-\d+px/);
  });

  it("marks the section being read and unmarks the others", async () => {
    w = open();
    expect(marked(w)).toEqual(["#vehicle"]);

    for (const id of ["trips", "fuel", "vehicle", "fuel"]) {
      await reach(id);
      expect(marked(w)).toEqual([`#${id}`]);
      expect(announced(w)).toEqual([`#${id}`]);
    }
  });

  it("keeps one highlight when sections share the band, by reading order", async () => {
    // The desktop grid puts the fuel card on the same top row as the vehicle
    // card, so two sections are legitimately in the band at once.
    w = open();
    await reach("vehicle", "fuel");
    expect(marked(w)).toEqual(["#vehicle"]);
    await reach("trips", "fuel");
    expect(marked(w)).toEqual(["#trips"]);
  });

  it("pins the highlight to a clicked item until the reader scrolls by hand", async () => {
    w = open();
    await links(w)[2].trigger("click");
    await settle();
    expect(marked(w)).toEqual(["#fuel"]);

    // Clicking "fuel" at desktop scrolls to the shared top row, so the spy
    // reports the vehicle card. Without the pin the highlight would snap back.
    await reach("vehicle");
    expect(marked(w)).toEqual(["#fuel"]);

    window.dispatchEvent(new Event("wheel"));
    await reach("vehicle");
    expect(marked(w)).toEqual(["#vehicle"]);
  });

  it("honours a deep link on load and a back/forward hash change", async () => {
    window.history.replaceState(null, "", "#trips");
    w = open();
    // The fragment is read in onMounted, so the highlight lands on the tick after
    // the first paint, not during it.
    await nextTick();
    expect(marked(w)).toEqual(["#trips"]);

    window.history.replaceState(null, "", "#fuel");
    window.dispatchEvent(new Event("hashchange"));
    await nextTick();
    expect(marked(w)).toEqual(["#fuel"]);
  });

  it("stops observing when the page is torn down", () => {
    w = open();
    const o = spy();
    w.unmount();
    w = null;
    expect(o.live).toBe(false);
  });
});
