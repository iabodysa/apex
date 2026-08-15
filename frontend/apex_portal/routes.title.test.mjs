import { afterEach, describe, expect, it } from "vitest";
import { createMemoryHistory } from "vue-router";

import { mountPortal } from "./main.js";
import { createPortalRouter, getPortalContext } from "./core/router.js";
import { portalRoutes as routes } from "./routes.js";

// A portal route's document title is built in main.js from `meta.label`, so a route without one
// falls back to the context name and two screens become indistinguishable in history, in a
// bookmark, and in a shared tab. The redirect entries carry no page of their own and are exempt.
const flatten = (list, prefix = "") =>
  (list || []).flatMap((route) => {
    const path = prefix + (route.path || "");
    const self = {
      path, name: route.name, label: route.meta?.label,
      feature: route.feature, redirect: route.redirect,
    };
    return [self, ...flatten(route.children, path)];
  });

const all = flatten(routes);
const pages = all.filter((route) => !route.redirect);

describe("portal route titles", () => {
  it("every page route carries the label its title is built from", () => {
    const missing = pages.filter((route) => !route.label).map((route) => route.name || route.path);
    expect(missing).toEqual([]);
  });

  // A label repeats across personas on purpose — العهد is a worker destination and a housing one.
  // What must not repeat is the TITLE, which main.js composes from the label and the feature.
  it("no two page routes produce the same document title", () => {
    const counted = new Map();
    for (const route of pages) {
      const title = `${route.label} · ${route.feature}`;
      counted.set(title, (counted.get(title) || 0) + 1);
    }
    const shared = [...counted].filter(([, times]) => times > 1).map(([title]) => title);
    expect(shared).toEqual([]);
  });

  // The two checks above read the RAW route array. vue-router does not hand that array to a
  // navigation guard: `normalizeRouteRecord` rebuilds every record from a closed field list
  // (node_modules/vue-router/dist/vue-router.mjs:778), so a custom top-level key never reaches
  // the resolved location. Asserting the disambiguator only on the raw array is how it came to
  // be read from a property that is always undefined at runtime.
  it("carries the feature through resolution, where the title is composed", async () => {
    const router = createPortalRouter({
      context: getPortalContext("housing"),
      capabilities: ["estate_read", "safety_read"],
      routes,
      history: createMemoryHistory(),
    });
    await router.push("/beds");
    await router.isReady();
    expect(router.currentRoute.value.feature).toBeUndefined();
    expect(router.currentRoute.value.meta.feature).toBe("housing");

    await router.push("/rounds");
    expect(router.currentRoute.value.meta.feature).toBe("safety");
  });
});

const BOOTSTRAP = Object.freeze({
  entry: "housing",
  public_path: "/housing",
  initial_route: "/today",
  capabilities: ["today", "estate_read", "safety_read"],
  site_name: "portal.test",
  socketio_port: 9000,
  async_enabled: false,
  language: "ar",
  subject_scope: "portaltest12345678",
});

// These drive the real `mountPortal`, so they assert the title a browser tab would show rather
// than re-deriving it. Each mount gets its own memory history: jsdom keeps one global history
// across a file, so hash-history mounts inherit the previous test's entries and Back lands on
// another test's screen.
describe("portal document title", () => {
  let mounted;
  let target;

  const open = async (initialRoute) => {
    target = globalThis.document.createElement("div");
    globalThis.document.body.append(target);
    mounted = await mountPortal({
      source: { ...BOOTSTRAP, initial_route: initialRoute },
      target,
      history: createMemoryHistory(),
    });
    return mounted;
  };

  afterEach(() => {
    mounted?.application.unmount();
    target?.remove();
    mounted = undefined;
  });

  it("titles a direct link from the route it opened on, not the persona alone", async () => {
    await open("/rounds");
    expect(globalThis.document.title).toBe("جولات السلامة · إدارة السكن | أبكس");
  });

  it("retitles on every navigation, including going back", async () => {
    const { router } = await open("/beds");
    expect(globalThis.document.title).toBe("الغرف والأسرّة · إدارة السكن | أبكس");

    await router.push("/rounds");
    expect(globalThis.document.title).toBe("جولات السلامة · إدارة السكن | أبكس");

    // `back` only hands the history a new position; the router resolves the navigation it
    // triggers asynchronously, and `isReady` is already settled by then, so it waits on nothing.
    const returned = new Promise((resolve) => {
      const stop = router.afterEach(() => {
        stop();
        resolve();
      });
    });
    router.back();
    await returned;
    expect(globalThis.document.title).toBe("الغرف والأسرّة · إدارة السكن | أبكس");
  });

  it("gives the refusal its own title instead of the landing screen's", async () => {
    const { router } = await open("/beds");
    const landing = globalThis.document.title;

    await router.push("/custody");
    expect(globalThis.document.title).toBe("لا تملك صلاحية · إدارة السكن | أبكس");
    expect(globalThis.document.title).not.toBe(landing);
  });
});
