// Copyright (c) 2026, AFMCO and contributors
// Guards the shared token layer — the one file every portal's appearance resolves
// through. Three failures this replaces, all of which shipped for months:
//
//   1. A portal referenced var(--x) for an --x nothing declared. The property
//      silently resolved to nothing, so a tap target collapsed to content height
//      and a colour fell back to the UA default. The existing duplication guard
//      hashes whole FILES, so it cannot see a missing property.
//   2. The dark palette is authored twice (the prefers-color-scheme block and the
//      explicit [data-theme="dark"] toggle cannot be one rule), and the two copies
//      drifted — a correction landed in one and not the other.
//   3. Auto-dark was gated by a DENY-list that excluded the default-identity alias,
//      so four portals could never follow the OS however clean their stylesheet was.
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const SHARED = dirname(dirname(fileURLToPath(import.meta.url)));
const FRONTEND = dirname(SHARED);
const TOKENS = readFileSync(join(SHARED, "tokens.css"), "utf8");

// Properties a portal may reference without declaring: set at runtime by a
// component's :style binding, or an intentionally-optional opt-in with a fallback.
const RUNTIME_PROPS = new Set([
  "--ts-accent", // TabletSupervisorShell, from its `accent` prop
  "--ts-nav-w", // TabletSupervisorShell, from its `navWidth` prop
  "--mc-width", // MobileConsoleShell, from its `maxWidth` prop
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
  it("declares every custom property any portal or shared component references", () => {
    const shared = declaredIn(TOKENS);
    // A portal may alias the shared tokens into a private vocabulary in its own
    // src/index.css (fleet_os does: --t1: var(--c-ink)). That file is in scope for
    // every file of that portal — but for no other portal, which is the drift this
    // guard exists to catch.
    const portalScope = new Map();
    const scopeFor = (file) => {
      const portal = file.slice(FRONTEND.length + 1).split("/")[0];
      if (!portalScope.has(portal)) {
        let names = new Set();
        try {
          names = declaredIn(readFileSync(join(FRONTEND, portal, "src", "index.css"), "utf8"));
        } catch {
          /* portal has no stylesheet of its own — shared tokens only */
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

  it("keeps the two dark blocks identical, because they cannot be merged into one rule", () => {
    const auto = declarations(ruleBody(TOKENS, ':root:not([data-theme]),\n  :root[data-theme="afmco"]'));
    const explicit = declarations(ruleBody(TOKENS, ':root[data-theme="dark"]'));

    expect(Object.keys(auto).length).toBeGreaterThan(20);
    expect(auto).toEqual(explicit);
  });

  it("reaches auto-dark through an allow-list, never a :not() deny-list", () => {
    const media = TOKENS.slice(TOKENS.indexOf("@media (prefers-color-scheme: dark)"));
    const selector = media.slice(0, media.indexOf("{", media.indexOf("{") + 1));

    // The default identity has two spellings — no attribute, and the "afmco" alias
    // four wrappers server-render. Both must be repainted.
    expect(selector).toContain(":root:not([data-theme])");
    expect(selector).toContain(':root[data-theme="afmco"]');
    // A deny-list would hand dark primitives to the off-identity LIGHT themes
    // (frappe, atelier) while their own semantic tokens stayed light.
    expect(selector).not.toContain(':not([data-theme="afmco"])');
  });

  it("pins the contrast-corrected values, so a revert has to be deliberate", () => {
    const light = declarations(ruleBody(TOKENS, ":root,\n[data-theme=\"afmco\"],\n:root[data-theme=\"light\"]"));
    const dark = declarations(ruleBody(TOKENS, ':root[data-theme="dark"]'));

    // Ink tokens measured against the ground they are actually drawn on.
    expect(light["--warn"]).toBe("#8a5a10"); // 4.97:1 on --warn-bg, was 2.57:1
    expect(light["--ok"]).toBe("#046b41"); // 5.50:1 on --ok-bg, was 3.97:1
    expect(light["--danger"]).toBe("#a52d21"); // 5.39:1 on --danger-bg, was 4.18:1
    expect(light["--muted"]).toBe("#586962"); // 4.54:1 worst ground, was 3.33:1
    expect(dark["--muted"]).toBe("#94a69a");
    expect(dark["--danger"]).toBe("#f5867a");
    // In dark, --info used to equal --ok exactly: an "in progress" pill and a
    // "done" pill rendered pixel-identical at 1.00:1.
    expect(dark["--info"]).not.toBe(dark["--ok"]);

    // The ink on a danger fill follows the mode. White clears the light red at
    // 7.01:1 but only reaches 2.45:1 on the lighter dark red, where forest ink
    // reaches 7.77:1 — so it cannot be one mode-independent value.
    expect(light["--danger-ink"]).toBe("#ffffff");
    expect(dark["--danger-ink"]).toBe("#04130c");
  });

  // Repainting every --c-* still leaves the parts CSS cannot reach — scrollbars, the
  // canvas behind the document, native select and date pickers — on their light
  // defaults. Only color-scheme moves those, and it has to move in all three blocks.
  it("declares color-scheme alongside the palette in every mode", () => {
    const light = TOKENS.slice(0, TOKENS.indexOf("@media (prefers-color-scheme: dark)"));
    const media = TOKENS.slice(TOKENS.indexOf("@media (prefers-color-scheme: dark)"));

    // The lookbehind matters: "prefers-color-scheme: dark" contains the declaration
    // as a substring, so a naive count reads the @media header as a third mode.
    expect(light).toContain("color-scheme: light");
    expect(media.match(/(?<!prefers-)color-scheme: dark/g) || []).toHaveLength(2);
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
