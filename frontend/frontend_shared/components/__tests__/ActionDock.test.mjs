// Copyright (c) 2026, afmcoltd
import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import ActionDock from "@shared/components/ActionDock.vue";

const SOURCE = fs.readFileSync(
  path.resolve(import.meta.dirname, "../ActionDock.vue"),
  "utf8",
);
const dock = (slots) => mount(ActionDock, { slots });
const order = (w) => w.findAll(".action-dock > div").map((el) => el.classes()[0]);

describe("ActionDock", () => {
  it("puts the primary last, after the danger and the secondary", () => {
    const w = dock({
      danger: "<button class='d'>Delete</button>",
      secondary: "<button class='s'>Back</button>",
      primary: "<button class='p'>Save</button>",
    });
    expect(order(w)).toEqual([
      "action-dock-danger",
      "action-dock-secondary",
      "action-dock-primary",
    ]);
  });

  it("stacks in the same order it reads, so the eye and the keyboard agree", () => {
    expect(SOURCE).not.toContain("column-reverse");
    const w = dock({ secondary: "<span class='s'>why</span>", primary: "<button class='p'>Go</button>" });
    expect(order(w)).toEqual(["action-dock-secondary", "action-dock-primary"]);
  });

  it("draws only the slots it is given", () => {
    const w = dock({ primary: "<button class='p'>Go</button>" });
    expect(order(w)).toEqual(["action-dock-primary"]);
  });
});
