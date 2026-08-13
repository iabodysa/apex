import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { housingRoutes } from "./routes.js";
import { nextCustodySelection } from "./custodyState.js";

const read = (name) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");

describe("housing feature contract", () => {
  it("ships every approved housing route exactly once", () => {
    expect(housingRoutes.map((route) => route.path)).toEqual([
      "/overview", "/today", "/count", "/count/:item", "/beds", "/beds/:bed",
      "/arrivals", "/transfer", "/custody", "/delivery", "/delivery/:name",
      "/maintenance", "/maintenance/new", "/maintenance/:name",
    ]);
    expect(new Set(housingRoutes.map((route) => route.name)).size).toBe(housingRoutes.length);
  });

  it("loads every housing page module", async () => {
    const pages = await Promise.all(housingRoutes.map((route) => route.component()));
    expect(pages).toHaveLength(housingRoutes.length);
    expect(pages.every((page) => page.default)).toBe(true);
  });

  it("keeps overview and creation routes out of the primary navigation and groups operations by domain", () => {
    const navigation = housingRoutes.filter((route) => route.meta.navigation);
    expect(navigation.map((route) => route.path)).not.toContain("/overview");
    expect(navigation.map((route) => route.path)).not.toContain("/maintenance/new");
    expect(navigation.find((route) => route.path === "/count").meta.group).toBe("العهد والجرد");
    expect(navigation.find((route) => route.path === "/custody").meta.group).toBe("العهد والجرد");
    expect(navigation.find((route) => route.path === "/delivery").meta.group).toBe("العهد والجرد");
  });

  it("clears holder and cart when building changes", () => {
    const state = {
      building: "BLD-A",
      holder: { party_type: "Employee", party: "EMP-1" },
      cart: [{ article: "Blanket", qty: 1 }],
    };
    expect(nextCustodySelection(state, { building: "BLD-B" })).toEqual({
      building: "BLD-B", holder: null, cart: [],
    });
  });

  it("clears prior holder data and cart when holder changes", () => {
    const state = {
      building: "BLD-A",
      holder: { party_type: "Employee", party: "EMP-1" },
      cart: [{ article: "Blanket", qty: 1 }],
    };
    expect(nextCustodySelection(state, {
      holder: { party_type: "Temporary Worker", party: "TW-2" },
    })).toEqual({
      building: "BLD-A",
      holder: { party_type: "Temporary Worker", party: "TW-2" },
      cart: [],
    });
  });

  it("keeps long inventory notes readable instead of clipping them in one line", () => {
    const page = read("./pages/InventoryCountPage.vue");
    const css = read("./housing.css");
    expect(page).toContain('class="inventory-row__notes" type="textarea"');
    expect(css).toMatch(/\.inventory-row__notes textarea\s*\{[^}]*white-space:\s*pre-wrap/s);
    expect(css).toMatch(/@media \(max-width: 1100px\)[\s\S]*?\.inventory-row__notes\s*\{[^}]*grid-column:\s*1 \/ -1/s);
  });
});
