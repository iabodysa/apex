import { describe, expect, it } from "vitest";
import { housingRoutes } from "./routes.js";
import { nextCustodySelection } from "./custodyState.js";

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
});
