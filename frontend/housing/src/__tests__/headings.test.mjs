// Copyright (c) 2026, afmcoltd
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const APP = readFileSync(fileURLToPath(new URL("../App.vue", import.meta.url)), "utf8");
const TEMPLATE = APP.slice(APP.indexOf("<template>"), APP.indexOf("<script setup>"));
const STYLE = APP.slice(APP.indexOf("<style"));

function branch(marker, end) {
  const from = TEMPLATE.indexOf(marker);
  return from < 0 ? "" : TEMPLATE.slice(from, TEMPLATE.indexOf(end, from));
}

describe("housing portal heading contract", () => {
  it("gives every mutually exclusive shell branch its own h1", () => {
    expect(branch('class="desktop-context"', "</section>")).toContain("<h1>");
    expect(branch('class="building-stage"', "</section>")).toContain("<h1");
    expect(branch('class="scene-heading"', "</header>")).toContain("<h1>");
  });

  it("hides no heading, because the branch that hides one has no other", () => {
    // The desktop rail and the scene heading swap at 64rem and the picker replaces both,
    // so a display:none on an h1 leaves that width with no page title at all — which is
    // what `.desktop-context.is-narrow > h2` did to /count and /delivery at 1440.
    const hidden = STYLE.match(/[^}]*h1[^{}]*\{[^}]*display:\s*none[^}]*\}/g) || [];
    expect(hidden).toEqual([]);
  });
});
