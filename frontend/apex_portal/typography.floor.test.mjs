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

const walk = (dir, extension) =>
  readdirSync(dir).flatMap((entry) => {
    if (SKIP.has(entry)) return [];
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return walk(path, extension);
    return path.endsWith(extension) ? [path] : [];
  });

const sheets = walk(ROOT, ".css").map((path) => ({ path, text: readFileSync(path, "utf8") }));
const name = (path) => path.split("/").pop();
/** Declaration blocks, as `{ path, selector, body }`, so a rule's family and figures read together. */
const blocks = sheets.flatMap(({ path, text }) =>
  [...text.matchAll(/([^{}]*)\{([^{}]*)\}/g)].map(([, selector, body]) => ({
    path,
    selector: selector.trim(),
    body,
  })),
);

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

  // A `font-size: var(--fs-sm)` whose token was never defined is invalid at computed-value time:
  // the declaration is dropped and the element silently inherits 16px. The floor test above reads
  // literals, so it cannot see a size that is spelt as a token. This one closes that blind spot.
  it("every custom property a stylesheet reads is defined", () => {
    const defined = new Set(
      sheets.flatMap(({ text }) => [...text.matchAll(/^\s*(--[\w-]+)\s*:/gm)].map(([, token]) => token)),
    );
    const dangling = sheets.flatMap(({ path, text }) =>
      [...text.matchAll(/var\(\s*(--[\w-]+)\s*\)/g)]
        .filter(([, token]) => !defined.has(token))
        .map(([, token]) => `${name(path)} ${token}`),
    );
    expect([...new Set(dangling)]).toEqual([]);
  });

  // The identity fixes family by role, and figures belong to Thmanyah Sans: both serifs default to
  // oldstyle digits, so a KPI set in one dances on the baseline and breaks column alignment.
  it("figures never sit in a serif", () => {
    const serifFigures = blocks
      .filter(({ body }) => /font-variant-numeric/.test(body) && /var\(--font-(display|serif)\)/.test(body))
      .map(({ path, selector }) => `${name(path)} ${selector}`);
    expect(serifFigures).toEqual([]);
  });

  // The shells own the single H1 — MobileShell.vue and OperationsShell.vue each render one, titled
  // from the route. A feature page adding its own gives a route two top-level headings and moves
  // the document outline out of the shell that is supposed to hold it.
  it("no feature page declares its own H1", () => {
    const owners = walk(join(ROOT, "features"), ".vue")
      .filter((path) => /<h1[\s>]/.test(readFileSync(path, "utf8")))
      .map(name);
    expect(owners).toEqual([]);
  });
});
