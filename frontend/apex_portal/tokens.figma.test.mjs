import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Figma is the origin of the design — the owner ruled it on 2026-08-14 — so these seven primitives
// are transcribed from the Apex Colors collection in file MZC4qx4zo7sW3uIIRSeUCA and this test is
// what stops the stylesheet drifting away from it. Two had already drifted when it was written:
// accent-ink was aliased to the primary hover (#006f41) instead of carrying its own #006f42, and
// the border was #d8d0bd against Figma's #ddd5c2.
const FIGMA = {
  "--c-ink": "#072b1a",
  "--c-primary": "#00844e",
  "--c-accent-ink": "#006f42",
  "--c-surface": "#f8f5ee",
  "--c-canvas": "#e9e3d3",
  "--c-border": "#ddd5c2",
  "--c-mint": "#60d297",
};

const tokens = readFileSync(join(process.cwd(), "styles", "tokens.css"), "utf8");

describe("Apex Colors, transcribed from Figma", () => {
  for (const [name, value] of Object.entries(FIGMA)) {
    it(`${name} is ${value}`, () => {
      const declared = tokens.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, "i"))?.[1];
      expect(declared?.toLowerCase()).toBe(value);
    });
  }
});
