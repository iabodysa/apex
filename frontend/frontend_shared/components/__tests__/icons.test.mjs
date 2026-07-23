// Copyright (c) 2026, AFMCO and contributors
// Invariants for the shared icon geometry registry (icons.js). Pure data — no DOM.
import { describe, it, expect } from "vitest";
import * as icons from "@shared/components/icons.js";

const TAGS = new Set(["path", "circle", "rect", "line", "polyline", "polygon"]);

describe("icons.js registry", () => {
  const entries = Object.entries(icons);

  it("exports a non-trivial set of glyphs", () => {
    expect(entries.length).toBeGreaterThan(50);
  });

  it("every export is an ordered list of {tag, attrs} SVG children", () => {
    for (const [name, shape] of entries) {
      expect(Array.isArray(shape), `${name} is an array`).toBe(true);
      expect(shape.length, `${name} has children`).toBeGreaterThan(0);
      for (const child of shape) {
        expect(TAGS.has(child.tag), `${name}: tag ${child.tag} is a known SVG element`).toBe(true);
        expect(child.attrs && typeof child.attrs === "object", `${name}: attrs object`).toBe(true);
      }
    }
  });

  it("has no duplicate geometries (dedup invariant)", () => {
    const seen = new Map();
    for (const [name, shape] of entries) {
      const sig = JSON.stringify(shape);
      expect(seen.has(sig), `${name} duplicates ${seen.get(sig)}`).toBe(false);
      seen.set(sig, name);
    }
  });

  it("preserves a known geometry byte-for-byte (chevron)", () => {
    expect(icons.chevron).toEqual([{ tag: "path", attrs: { d: "m9 18 6-6-6-6" } }]);
  });

  it("keeps colliding same-name variants as distinct exports (calendar plain vs check)", () => {
    // fleet/safety drew a plain calendar; driver/worker a calendar-with-check.
    expect(icons.calendar).toBeDefined();
    expect(icons.calendar2).toBeDefined();
    expect(JSON.stringify(icons.calendar)).not.toBe(JSON.stringify(icons.calendar2));
  });
});
