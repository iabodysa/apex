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

// Fields whose value is a Frappe docname, a naming-series id or a scanned code — Latin in an
// Arabic paragraph. `driver_name`, `route_name` and `project_label` are deliberately absent:
// those carry human or translated text, where the paragraph direction is already right.
const IDENTIFIER_FIELD = /\b(?:bed_code|room_number|passport_number|plate_number|vehicle_plate|linked_maintenance_request|from_driver|to_driver|from_building|to_building|route_plan|dispatch_trip|sender)\b|\.(?:room|building|plate|employee)\b/;

const VOID_TAGS = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"]);
const TAG = /<(\/?)([a-zA-Z][\w.-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/?)>/g;

/**
 * Finds the character ranges of a template that sit inside a bidirectional isolate.
 *
 * Enclosure cannot be read line by line: `SimpleListPage.vue` opens its `<p dir="auto">` on one
 * line and interpolates on the next, so a per-line check would call an isolated value bare.
 *
 * @param {string} text the full single-file component source
 * @returns {Array<[number, number]>} start/end offsets covered by a `bdi` or a `dir="auto"` element
 */
function isolatedRanges(text) {
  const stack = [];
  const ranges = [];
  TAG.lastIndex = 0;
  let match = TAG.exec(text);
  while (match) {
    const [full, closing, name, attributes, selfClosing] = match;
    if (closing) {
      const opened = stack.findLastIndex((frame) => frame.name === name);
      if (opened >= 0) {
        if (stack[opened].isolating) ranges.push([stack[opened].end, match.index]);
        stack.length = opened;
      }
    } else if (!selfClosing && !VOID_TAGS.has(name.toLowerCase())) {
      stack.push({
        name,
        end: match.index + full.length,
        isolating: name.toLowerCase() === "bdi" || /\bdir\s*=\s*"auto"/.test(attributes),
      });
    }
    match = TAG.exec(text);
  }
  return ranges;
}

function bareIdentifiers({ path, text }) {
  const ranges = isolatedRanges(text);
  const found = [];
  for (const interpolation of text.matchAll(/\{\{[\s\S]*?\}\}/g)) {
    // A subscript is a lookup key, not output: `ratingMessages[trip.dispatch_trip]` prints an
    // Arabic sentence, and isolating it would mark a value the reader never sees.
    if (!IDENTIFIER_FIELD.test(interpolation[0].replace(/\[[^\]]*\]/g, ""))) continue;
    const at = interpolation.index;
    if (ranges.some(([start, end]) => at >= start && at < end)) continue;
    const line = text.slice(0, at).split("\n").length;
    found.push(`${path.slice(ROOT.length + 1)}:${line}`);
  }
  return found;
}

describe("bidirectional isolation", () => {
  it("the portal isolates record identifiers rather than trusting the paragraph direction", () => {
    const isolated = sources.reduce(
      (total, { text }) =>
        total + (text.match(/<bdi\b/g)?.length || 0) + (text.match(/dir="auto"/g)?.length || 0),
      0,
    );
    // The floor sits just under the real count on purpose. A wide margin lets a whole page lose
    // its isolation while the total still clears the bar — which is what a slack guard buys you.
    expect(isolated).toBeGreaterThanOrEqual(180);
  });

  it("every component that prints a record reference isolates it", () => {
    const bare = sources
      .filter(({ text }) => text.includes("record-reference"))
      .filter(({ text }) => !/<bdi\b|dir="auto"/.test(text))
      .map(({ path }) => path.split("/").pop());
    expect(bare).toEqual([]);
  });

  // The two checks above are satisfied by isolation ANYWHERE in a file, which is how a page could
  // isolate its title and leave the plate beside it bare. This one resolves each interpolation
  // against the element that actually encloses it.
  it("no interpolated record identifier renders outside an isolate", () => {
    expect(sources.flatMap(bareIdentifiers)).toEqual([]);
  });

  it("truncation is expressed in logical properties, so it clips at the visual end in either script", () => {
    const foundation = readFileSync(join(ROOT, "styles", "foundation.css"), "utf8");
    expect(foundation).toContain("text-overflow: ellipsis");
    expect(foundation).toContain("min-inline-size: 0");
    expect(foundation).not.toContain("min-width: 0");
  });
});
