// Copyright (c) 2026, AFMCO and contributors
//
// Runtime proof that the /fleet employee nav LEADS SOMEWHERE REAL.
//
// The nav used to be three same-page anchors (#vehicle/#trips/#fuel) over a page
// that fit one screen, so every link was decorative. It is now a vue-router nav
// over real pages, and that is what is asserted here: every header link resolves
// to a registered route, following one swaps the routed page, and the active
// state (`is-active` + aria-current="page") marks exactly the page being shown.
//
// It lives in the shared harness because that is the one frontend suite CI runs
// (`npm test -w frontend_shared`, Portal Tests / shared-components); fleet ships
// a bundle, not a test runner.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

// The pages' only real boundary: the identity-scoped fleet_employee endpoints.
// Stubbed so the mount needs no bench. The pages render whatever the data layer
// answers, so the nav is fully exercised on an empty account.
vi.mock("@shared/call", () => ({
  configureApi: () => {},
  call: vi.fn(async () => null),
}));

import App from "../../../fleet/src/App.vue";
import router from "../../../fleet/src/router.js";

const links = (w) => w.findAll(".fleet-nav a");
const hrefs = (w) => links(w).map((a) => a.attributes("href"));
const marked = (w) =>
  links(w)
    .filter((a) => a.classes("is-active"))
    .map((a) => a.attributes("href"));
const announced = (w) =>
  links(w)
    .filter((a) => a.attributes("aria-current") === "page")
    .map((a) => a.attributes("href"));

describe("/fleet employee nav", () => {
  let w = null;

  beforeEach(async () => {
    // A fragment left by a previous test's navigation would deep-link the next
    // mount (hash history reads location.hash on startup).
    window.history.replaceState(null, "", "/");
    await router.replace("/");
    await router.isReady();
  });

  afterEach(() => {
    if (w) w.unmount();
    w = null;
  });

  const open = async () => {
    const wrapper = mount(App, { global: { plugins: [router] } });
    await flushPromises();
    return wrapper;
  };

  it("offers only real routes — no same-page anchors, no dead hrefs", async () => {
    w = await open();
    const targets = hrefs(w);
    expect(targets).toEqual(["#/", "#/trips", "#/fuel"]);
    for (const href of targets) {
      // "#/x" is a hash-history ROUTE; "#x" would be a same-page anchor again.
      expect(href).toMatch(/^#\//);
      const resolved = router.resolve(href.slice(1));
      expect(resolved.matched.length).toBeGreaterThan(0);
      expect(resolved.name).not.toBe(undefined);
    }
  });

  it("marks the page being shown and unmarks the others", async () => {
    w = await open();
    expect(marked(w)).toEqual(["#/"]);
    expect(announced(w)).toEqual(["#/"]);

    for (const path of ["/trips", "/fuel", "/"]) {
      await router.push(path);
      await flushPromises();
      const href = "#" + path;
      expect(marked(w)).toEqual([href]);
      expect(announced(w)).toEqual([href]);
    }
  });

  it("following a link swaps the routed page for real", async () => {
    w = await open();
    // Home: the vehicle/preview cards, not the fuel form.
    expect(w.find(".emp-grid").exists()).toBe(true);
    expect(w.find("#ff-litres").exists()).toBe(false);

    await links(w)[1].trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/trips");
    // The trips page owns the full list column (empty state on a stubbed
    // account — a non-driver employee legitimately has no trips).
    expect(w.find(".emp-narrow").exists()).toBe(true);
    expect(w.find(".emp-grid").exists()).toBe(false);

    await links(w)[2].trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/fuel");
    // The fuel page owns the request form.
    expect(w.find("#ff-litres").exists()).toBe(true);

    await links(w)[0].trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/");
    expect(w.find("#ff-litres").exists()).toBe(false);
  });

  it("redirects an unknown path home instead of rendering nothing", async () => {
    w = await open();
    await router.push("/no-such-page");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/");
    expect(marked(w)).toEqual(["#/"]);
  });
});
