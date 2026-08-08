// Copyright (c) 2026, AFMCO and contributors
//
// A-392 — the strings the product says the same way must actually be the same.
//
// The check is NOT "no shared key differs between portals". Most shared keys are
// supposed to differ: `boarding.hint` tells the driver to point the camera at a
// worker's pass and tells the worker to show theirs, and `errors.loadFailed` names the
// thing each portal failed to load. Collapsing those would be the defect, not the fix.
//
// What must not differ is the set SHARED_MESSAGES claims: the connection and session
// messages that have nothing to do with what a portal is for. This asserts that no
// portal re-defines one of those keys, so every portal resolves the same sentence.

import assert from "node:assert/strict";
import { readdirSync, existsSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { SHARED_MESSAGES } from "./sharedMessages.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

function extractMessages(source) {
  const start = source.indexOf("const messages = {");
  if (start === -1) return null;
  return extractLiteral(source, source.indexOf("{", start));
}

function extractLiteral(source, open) {
  let depth = 0;
  let inStr = null;
  let inComment = null;
  for (let i = open; i < source.length; i++) {
    const c = source[i];
    if (inComment === "line") {
      if (c === "\n") inComment = null;
      continue;
    }
    if (inComment === "block") {
      if (c === "*" && source[i + 1] === "/") {
        inComment = null;
        i++;
      }
      continue;
    }
    if (inStr) {
      if (c === "\\") i++;
      else if (c === inStr) inStr = null;
      continue;
    }
    if (c === "/" && source[i + 1] === "/") {
      inComment = "line";
      i++;
      continue;
    }
    if (c === "/" && source[i + 1] === "*") {
      inComment = "block";
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") inStr = c;
    else if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) return source.slice(open, i + 1);
    }
  }
  return null;
}

function flatten(obj, prefix = "", out = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) flatten(v, key, out);
    else if (typeof v === "string") out[key] = v;
  }
  return out;
}

function extractDefault(source) {
  const start = source.indexOf("export default {");
  if (start === -1) return null;
  return extractLiteral(source, source.indexOf("{", start));
}

// A portal keeps its strings either in one src/i18n.js keyed by locale, or in a
// src/i18n/ directory with a file per locale. Both shapes must be read, or a portal
// that splits its locales silently drops out of this check instead of failing it.
function readMessages(portal) {
  const single = join(ROOT, portal, "src", "i18n.js");
  if (existsSync(single)) {
    const literal = extractMessages(readFileSync(single, "utf8"));
    assert.ok(literal, `${portal}: could not read its messages literal`);
    return new Function(`return ${literal}`)();
  }
  const dir = join(ROOT, portal, "src", "i18n");
  const messages = {};
  for (const file of readdirSync(dir)) {
    if (!file.endsWith(".js") || ["index.js", "enums.js"].includes(file)) continue;
    const literal = extractDefault(readFileSync(join(dir, file), "utf8"));
    assert.ok(literal, `${portal}/${file}: could not read its default export`);
    messages[file.slice(0, -3)] = new Function(`return ${literal}`)();
  }
  return messages;
}

const portals = readdirSync(ROOT, { withFileTypes: true })
  .filter((d) => d.isDirectory() && !["frontend_shared", "node_modules"].includes(d.name))
  .map((d) => d.name)
  .filter(
    (p) =>
      existsSync(join(ROOT, p, "src", "i18n.js")) || existsSync(join(ROOT, p, "src", "i18n")),
  );

const loaded = portals.map((portal) => [portal, readMessages(portal)]);

test("every portal's i18n was actually read", () => {
  assert.equal(loaded.length, portals.length);
  assert.ok(portals.length >= 7, `expected all portals, saw ${portals.join(", ")}`);
});

for (const locale of Object.keys(SHARED_MESSAGES)) {
  const owned = Object.keys(flatten(SHARED_MESSAGES[locale]));
  test(`no portal re-defines a shared ${locale} string`, () => {
    const offenders = [];
    for (const [portal, messages] of loaded) {
      const flat = flatten(messages[locale]);
      for (const key of owned) {
        if (key in flat && flat[key] !== flatten(SHARED_MESSAGES[locale])[key]) {
          offenders.push(`${portal}.${key} = ${JSON.stringify(flat[key])}`);
        }
      }
    }
    assert.deepEqual(
      offenders,
      [],
      "a portal overrides a shared string with different text; either delete the "
        + "override so it inherits, or move the key out of SHARED_MESSAGES because "
        + "it genuinely differs per portal",
    );
  });
}

test("both locales define exactly the same shared keys", () => {
  const en = Object.keys(flatten(SHARED_MESSAGES.en)).sort();
  const ar = Object.keys(flatten(SHARED_MESSAGES.ar)).sort();
  assert.deepEqual(ar, en, "an Arabic shared string is missing or unpaired");
});
