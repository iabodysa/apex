import { describe, expect, it } from "vitest";

import { routes } from "./routes.js";

// A portal route's document title is built in main.js from `meta.label`, so a route without one
// falls back to the context name and two screens become indistinguishable in history, in a
// bookmark, and in a shared tab. The redirect entries carry no page of their own and are exempt.
const flatten = (list, prefix = "") =>
  (list || []).flatMap((route) => {
    const path = prefix + (route.path || "");
    const self = { path, name: route.name, label: route.meta?.label, redirect: route.redirect };
    return [self, ...flatten(route.children, path)];
  });

const all = flatten(routes);
const pages = all.filter((route) => !route.redirect);

describe("portal route titles", () => {
  it("every page route carries the label its title is built from", () => {
    const missing = pages.filter((route) => !route.label).map((route) => route.name || route.path);
    expect(missing).toEqual([]);
  });

  it("no two page routes share a label", () => {
    const counted = new Map();
    for (const route of pages) counted.set(route.label, (counted.get(route.label) || 0) + 1);
    const shared = [...counted].filter(([, times]) => times > 1).map(([label]) => label);
    expect(shared).toEqual([]);
  });
});
