import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// The portal is RTL. A Latin record identifier — a plate, a request id, an employee code — placed
// unisolated inside Arabic text has its parts reordered by the bidi algorithm, which is how
// "TR-...PROJ-..." came to render glued and backwards. `bdi` and `dir="auto"` are the native
// isolation; this holds the count from falling back.
const ROOT = process.cwd();
const SKIP = new Set(["node_modules", "dist", "__pycache__"]);

const walk = (dir) =>
  readdirSync(dir).flatMap((entry) => {
    if (SKIP.has(entry)) return [];
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return walk(path);
    return path.endsWith(".vue") ? [path] : [];
  });

const sources = walk(ROOT).map((path) => ({ path, text: readFileSync(path, "utf8") }));

describe("bidirectional isolation", () => {
  it("the portal isolates record identifiers rather than trusting the paragraph direction", () => {
    const isolated = sources.reduce(
      (total, { text }) =>
        total + (text.match(/<bdi\b/g)?.length || 0) + (text.match(/dir="auto"/g)?.length || 0),
      0,
    );
    // The floor sits just under the real count on purpose. A wide margin lets a whole page lose
    // its isolation while the total still clears the bar — which is what a slack guard buys you.
    expect(isolated).toBeGreaterThanOrEqual(134);
  });

  it("every component that prints a record reference isolates it", () => {
    const bare = sources
      .filter(({ text }) => text.includes("record-reference"))
      .filter(({ text }) => !/<bdi\b|dir="auto"/.test(text))
      .map(({ path }) => path.split("/").pop());
    expect(bare).toEqual([]);
  });

  it("truncation is expressed in logical properties, so it clips at the visual end in either script", () => {
    const foundation = readFileSync(join(ROOT, "styles", "foundation.css"), "utf8");
    expect(foundation).toContain("text-overflow: ellipsis");
    expect(foundation).toContain("min-inline-size: 0");
    expect(foundation).not.toContain("min-width: 0");
  });
});
