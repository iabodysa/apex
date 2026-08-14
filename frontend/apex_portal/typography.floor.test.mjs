import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// A worker reads this on a phone in a corridor. The identity sets 13px as the floor for anything
// he has to read, and .78rem — 12.48px — sat under it in five stylesheets before this test existed.
// Headings are the display serif by role, not by page; a shell that reassigns them breaks the
// identity everywhere at once, so that is asserted rather than trusted.
const ROOT = process.cwd();
const SKIP = new Set(["node_modules", "dist", "__pycache__"]);
const FLOOR_REM = 13 / 16;

const walk = (dir) =>
  readdirSync(dir).flatMap((entry) => {
    if (SKIP.has(entry)) return [];
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return walk(path);
    return path.endsWith(".css") ? [path] : [];
  });

const sheets = walk(ROOT).map((path) => ({ path, text: readFileSync(path, "utf8") }));

describe("portal typography", () => {
  it("nothing a worker reads falls below the 13px floor", () => {
    const under = [];
    for (const { path, text } of sheets) {
      for (const [, size] of text.matchAll(/font-size:\s*(\d*\.?\d+)rem/g)) {
        if (Number(size) < FLOOR_REM) under.push(`${path.split("/").pop()} ${size}rem`);
      }
      for (const [, size] of text.matchAll(/font-size:\s*(\d+)px/g)) {
        if (Number(size) < 13) under.push(`${path.split("/").pop()} ${size}px`);
      }
    }
    expect(under).toEqual([]);
  });

  it("headings keep the display serif", () => {
    const foundation = readFileSync(join(ROOT, "styles", "foundation.css"), "utf8");
    expect(foundation).toMatch(/h1,\s*h2,\s*h3\s*{[^}]*font-family:\s*var\(--font-display\)/);
  });
});
