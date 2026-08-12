// Copyright (c) 2026, Apex contributors
// Guards the shared token layer — the one file every portal's appearance resolves
// through. Two failures this replaces, both of which shipped for months:
//
//   1. A portal referenced var(--x) for an --x nothing declared. The property
//      silently resolved to nothing, so a tap target collapsed to content height
//      and a colour fell back to the UA default. The existing duplication guard
//      hashes whole FILES, so it cannot see a missing property.
//   2. Multiple theme branches drifted and repainted the same semantic vocabulary.
//      Apex now ships one light palette; portal identity overrides only the accent.
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const SHARED = dirname(dirname(fileURLToPath(import.meta.url)));
const FRONTEND = dirname(SHARED);
const TOKENS = readFileSync(join(SHARED, "tokens.css"), "utf8");
const FRAPPE_UI_THEME = readFileSync(join(SHARED, "frappe-ui-theme.css"), "utf8");

// Properties a portal may reference without declaring: set at runtime by a
// component's :style binding, or an intentionally-optional opt-in with a fallback.
const RUNTIME_PROPS = new Set([
  "--ts-accent", // TabletSupervisorShell, from its `accent` prop
  "--ts-nav-w", // TabletSupervisorShell, from its `navWidth` prop
  "--mc-width", // MobileConsoleShell, from its `maxWidth` prop
  "--fleet-content-limit", // FleetPageShell, from its `maxWidth` compatibility prop
  "--fleet-header-offset", // FleetPageShell, shared sticky-header contract for fleet portals
  "--shell-wide", // opt-in: a portal widens the phone column at --bp-tablet
]);

function declaredIn(css) {
  return new Set([...css.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)].map((m) => m[1]));
}

function referencedIn(css) {
  return [...css.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)/g)].map((m) => m[1]);
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "dist" || entry === ".git") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if ([".css", ".vue"].includes(extname(full))) out.push(full);
  }
  return out;
}

/** The declaration body of the first rule whose selector list matches `selector`. */
function ruleBody(css, selector) {
  const at = css.indexOf(selector);
  expect(at, `selector not found in tokens.css: ${selector}`).toBeGreaterThan(-1);
  const open = css.indexOf("{", at);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

/** name -> value pairs, comments and whitespace discarded, for comparing two blocks. */
function declarations(body) {
  const out = {};
  for (const m of body.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g)) {
    out[m[1]] = m[2].trim().replace(/\s+/g, " ");
  }
  return out;
}

describe("shared token layer", () => {
  it("assigns each licensed brand family one role without bundling the server-owned font assets", () => {
    const light = declarations(ruleBody(TOKENS, ":root"));

    expect(TOKENS).not.toContain("thmanyah-v1/thmanyah.css");
    expect(light["--font"]).toBe('"Thmanyah Sans"');
    expect(light["--font-num"]).toBe("var(--font)");
    expect(light["--font-num-ar"]).toBe("var(--font)");
    expect(light["--font-display"]).toBe('"Thmanyah Serif Display"');
    expect(light["--font-serif"]).toBe('"Thmanyah Serif Text"');
    expect(light["--fw-heading"]).toBe("700");
    expect(light["--fw-semibold"]).toBe("700");
    expect(TOKENS).not.toMatch(/"Montserrat"|"Cairo"|system-ui|ui-monospace|"SF Mono"|"Menlo"|monospace/);
  });

  it("establishes a viewport-safe root before portal layouts add their own composition", () => {
    expect(TOKENS).toMatch(/\*,\s*\*::before,\s*\*::after\s*\{[^}]*box-sizing:\s*border-box/s);
    expect(TOKENS).toMatch(/html,\s*body,\s*#app\s*\{[^}]*min-inline-size:\s*0/s);
    expect(TOKENS).toMatch(/body\s*\{[^}]*overflow-x:\s*clip/s);
  });

  it("declares every custom property any portal or shared component references", () => {
    const shared = declaredIn(TOKENS + FRAPPE_UI_THEME);
    // A portal may alias the shared tokens into a private vocabulary in its own
    // src/index.css (fleet_os does: --t1: var(--c-ink)). That file is in scope for
    // every file of that portal — but for no other portal, which is the drift this
    // guard exists to catch.
    const portalScope = new Map();
    const scopeFor = (file) => {
      const portal = file.slice(FRONTEND.length + 1).split("/")[0];
      if (!portalScope.has(portal)) {
        let names = new Set();
        for (const relative of [["styles", "tokens.css"], ["src", "index.css"]]) {
          try {
            names = new Set([
              ...names,
              ...declaredIn(readFileSync(join(FRONTEND, portal, ...relative), "utf8")),
            ]);
          } catch {
            /* Optional portal token entry is absent. */
          }
        }
        portalScope.set(portal, names);
      }
      return portalScope.get(portal);
    };

    const offenders = [];
    for (const file of walk(FRONTEND)) {
      const css = readFileSync(file, "utf8");
      const local = declaredIn(css); // a component's own private var
      const portal = scopeFor(file);
      for (const name of referencedIn(css)) {
        if (shared.has(name) || local.has(name) || portal.has(name) || RUNTIME_PROPS.has(name)) continue;
        offenders.push(`${file.slice(FRONTEND.length + 1)} -> var(${name})`);
      }
    }

    expect([...new Set(offenders)].sort()).toEqual([]);
  });

  it("ships one light palette with no theme switch or OS dark branch", () => {
    const light = declarations(ruleBody(TOKENS, ":root"));

    expect(light["--brand-green"]).toBe("#00844e");
    expect(light["--mint"]).toBe("#60d297");
    expect(light["--forest"]).toBe("#072b1a");
    expect(light["--canvas"]).toBe("#e9e3d3");
    expect(light["--surface"]).toBe("#f8f5ee");
    expect(light["--muted"]).toBe("#47584f");
    expect(light["--border"]).toBe("#d8d0bd");
    expect(light["--ok"]).toBe("#14804a");
    expect(light["--warn"]).toBe("#a76609");
    expect(light["--danger"]).toBe("#b42318");
    expect(light["--info"]).toBe("#1266a0");
    expect(light["--ok-bg"]).toBe("color-mix(in srgb, var(--ok) 6%, var(--surface-2))");
    expect(light["--warn-bg"]).toBe("color-mix(in srgb, var(--warn) 1%, var(--surface-2))");
    expect(light["--danger-bg"]).toBe("color-mix(in srgb, var(--danger) 10%, var(--surface-2))");
    expect(light["--info-bg"]).toBe("color-mix(in srgb, var(--info) 10%, var(--surface-2))");
    expect(light["--danger-ink"]).toBe("#ffffff");
    expect(light["--radius-sm"]).toBe("8px");
    expect(light["--radius"]).toBe("14px");
    expect(light["--radius-lg"]).toBe("24px");
    expect(TOKENS).toContain("color-scheme: only light");
    expect(TOKENS).not.toContain("prefers-color-scheme");
    expect(TOKENS).not.toContain("data-theme");
    expect(TOKENS).not.toContain("color-scheme: dark");
  });

  it("ships one focus ring and one reduced-motion rule for every portal", () => {
    expect(TOKENS).toMatch(/:focus-visible\s*\{[^}]*outline:\s*3px solid var\(--c-focus\)/);
    expect(TOKENS).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
    // A collapse, not a removal: an entrance whose end state lives in `forwards`
    // must still land on that end state instead of leaving the element blank.
    expect(TOKENS).toContain("animation-duration: 0.01ms !important");
    expect(TOKENS).not.toMatch(/animation:\s*none\s*!important/);
  });
});
