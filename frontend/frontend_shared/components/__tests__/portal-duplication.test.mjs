// Copyright (c) 2026, AFMCO and contributors
// [#a281] Guard against byte-identical files drifting back across portal source
// trees. Twice now a review has independently rediscovered that the fleet and
// fleet_os trees shipped the same Icon.vue / LangToggle.vue / useToast.js; the
// second time, fleet's copies had gone STALE — its LangToggle styled itself from
// six CSS custom properties (--bg3, --b1, --blue, --r2, --r3, --t3) that exist
// only in fleet_os's stylesheet, so the live employee page rendered the language
// switcher with no pill, no border and no active-state highlight.
//
// A byte-identical pair across two portals is therefore treated as a DEFECT by
// default: either the file belongs in frontend_shared/ (imported BY DIRECT PATH,
// never through components/index.js — see that file for the A-041 barrel hazard),
// or it must be listed below with a reason naming what would break if merged.
import { describe, it, expect } from "vitest";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const HERE = path.dirname(new URL(import.meta.url).pathname);
const FRONTEND = path.resolve(HERE, "../../..");

const PORTALS = [
  "driver",
  "fleet",
  "fleet_os",
  "housing",
  "route_supervisor",
  "safety",
  "worker",
];

const SKIP_DIRS = new Set(["node_modules", ".vite", "dist"]);

// Build output, not source. The portal build writes these two stubs into every Vite
// root (frappe-ui's plugin turns on unplugin-auto-import + unplugin-vue-components),
// so whether they exist AT ALL depends on whether a build has run in this checkout:
// present after `npm run build`, absent in a fresh CI clone. Walking them would make
// this suite's verdict depend on that, and neither answer is stable — listing them in
// ALLOWED reds the stale-entry test in CI, omitting them reds the undocumented-group
// test after a local build. They are gitignored (frontend/.gitignore) for the same
// reason: only an editor ever reads them.
const SKIP_FILES = new Set(["auto-imports.d.ts", "components.d.ts"]);

// Documented duplicate groups. Key = the group's members as "portal:relpath",
// sorted and joined with " | ". Value = why merging them is wrong, not merely
// unnecessary. Anything NOT listed here fails the test.
const ALLOWED = new Map([
  [
    "fleet:src/api.js | fleet_os:src/api.js",
    "A one-line re-export of @shared/call. The implementation is already " +
      "single-sourced; merging would delete a module specifier, not duplicated logic.",
  ],
  // --- Pre-existing groups outside A-281's scope, kept because the tooling
  // --- requires a file at that exact path in each package.
  [
    "housing:postcss.config.js | safety:postcss.config.js | worker:postcss.config.js",
    "PostCSS resolves its config from the package root, so each portal needs its own.",
  ],
  [
    "driver:.gitignore | worker:.gitignore",
    "git applies ignore rules per directory; the file must sit in the dir it governs.",
  ],
  [
    "driver:src/assets/afmco-logo.svg | worker:public/afmco-logo.svg",
    "Same brand asset through two different pipelines: driver imports it as a " +
      "bundled module asset, worker serves it verbatim from public/ at a stable URL.",
  ],
]);

function walk(dir, base, out) {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (!SKIP_DIRS.has(entry)) walk(full, base, out);
    } else if (!SKIP_FILES.has(entry)) {
      out.push(path.relative(base, full));
    }
  }
}

function duplicateGroups() {
  const byHash = new Map();
  for (const portal of PORTALS) {
    const base = path.join(FRONTEND, portal);
    let files = [];
    try {
      walk(base, base, files);
    } catch {
      continue; // portal dir absent
    }
    for (const rel of files) {
      const hash = createHash("sha256")
        .update(readFileSync(path.join(base, rel)))
        .digest("hex");
      if (!byHash.has(hash)) byHash.set(hash, []);
      byHash.get(hash).push(`${portal}:${rel}`);
    }
  }
  const groups = [];
  for (const members of byHash.values()) {
    // Only cross-portal identity matters; two copies inside ONE portal are that
    // portal's own business.
    const portals = new Set(members.map((m) => m.split(":")[0]));
    if (portals.size > 1) groups.push(members.sort().join(" | "));
  }
  return groups.sort();
}

describe("portal source duplication", () => {
  it("has no byte-identical cross-portal file that is not documented", () => {
    const undocumented = duplicateGroups().filter((g) => !ALLOWED.has(g));
    expect(undocumented,
      "These files are byte-identical across portals with no recorded reason. " +
        "Move the shared part into frontend_shared/ and import it BY DIRECT PATH, " +
        "or add the group to ALLOWED in this file with a reason naming what would " +
        "break if it were merged.",
    ).toEqual([]);
  });

  it("has no stale entry in the documented list", () => {
    const actual = new Set(duplicateGroups());
    const stale = [...ALLOWED.keys()].filter((k) => !actual.has(k));
    expect(stale,
      "These groups are recorded as intentionally duplicated but are no longer " +
        "identical. Drop them from ALLOWED so the list keeps describing reality.",
    ).toEqual([]);
  });
});
