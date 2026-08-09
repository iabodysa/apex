// Copyright (c) 2026, AFMCO and contributors
// The theme switch is shared, and the thing that makes it shareable is how "Auto"
// behaves. Four wrappers server-render data-theme="{{ portal_theme or 'afmco' }}",
// so a toggle that implemented Auto as removeAttribute() would delete an
// administrator's configured theme the first time any worker tapped it — silently,
// permanently for that session, and with no way back short of a reload.
//
// SERVER_THEME is captured at module scope (before any click can write), so each
// case has to re-import the module with the DOM already in the state under test.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: "/", component: { template: "<div />" } }],
});
const mountToggle = (component) => mount(component, { global: { plugins: [router] } });

async function freshToggle(serverTheme) {
  const root = document.documentElement;
  if (serverTheme === null) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", serverTheme);
  vi.resetModules();
  return (await import("@shared/components/ThemeToggle.vue")).default;
}

const optionFor = (w, mode) => w.findAll(".theme-opt")[["light", "auto", "dark"].indexOf(mode)];

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("pins the chosen theme on <html>", async () => {
    const ThemeToggle = await freshToggle(null);
    const w = mountToggle(ThemeToggle);

    await optionFor(w, "dark").trigger("click");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    await optionFor(w, "light").trigger("click");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("restores the wrapper's theme on Auto instead of deleting it", async () => {
    const ThemeToggle = await freshToggle("afmco");
    const w = mountToggle(ThemeToggle);

    await optionFor(w, "dark").trigger("click");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    await optionFor(w, "auto").trigger("click");
    expect(document.documentElement.getAttribute("data-theme")).toBe("afmco");
  });

  it("keeps an administrator's non-default theme through a round trip", async () => {
    const ThemeToggle = await freshToggle("creative");
    const w = mountToggle(ThemeToggle);

    await optionFor(w, "light").trigger("click");
    await optionFor(w, "auto").trigger("click");
    expect(document.documentElement.getAttribute("data-theme")).toBe("creative");
  });

  it("removes the attribute on Auto only when the wrapper never set one", async () => {
    const ThemeToggle = await freshToggle(null);
    const w = mountToggle(ThemeToggle);

    await optionFor(w, "dark").trigger("click");
    await optionFor(w, "auto").trigger("click");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("re-applies the stored choice on mount and marks it pressed", async () => {
    localStorage.setItem("apex_theme", "dark");
    const ThemeToggle = await freshToggle("afmco");
    const w = mountToggle(ThemeToggle);
    await w.vm.$nextTick();

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(optionFor(w, "dark").attributes("aria-pressed")).toBe("true");
    expect(optionFor(w, "auto").attributes("aria-pressed")).toBe("false");
  });

  it("labels the group and every option through the portal's own dictionary", async () => {
    const ThemeToggle = await freshToggle(null);
    const w = mountToggle(ThemeToggle);

    expect(w.find(".theme-toggle").attributes("aria-label")).toBe("theme.label");
    expect(w.findAll(".theme-opt").map((b) => b.text())).toEqual([
      "theme.light",
      "theme.auto",
      "theme.dark",
    ]);
  });

  // Below --bp-phone the label is display:none and the glyph is aria-hidden, so
  // without this the three buttons have no accessible name at all on a phone.
  it("keeps an accessible name when the label is hidden on a phone", async () => {
    const ThemeToggle = await freshToggle(null);
    const w = mountToggle(ThemeToggle);

    expect(w.findAll(".theme-opt").map((b) => b.attributes("aria-label"))).toEqual([
      "theme.light",
      "theme.auto",
      "theme.dark",
    ]);
  });
});
