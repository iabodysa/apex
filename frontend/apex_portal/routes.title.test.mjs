import { describe, expect, it } from "vitest";

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
});
