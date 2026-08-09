// Copyright (c) 2026, AFMCO and contributors
// The shared LangToggle (driver/housing/safety) reads i18n through the `@/i18n`
// alias — here the test fixture — and flips the language on click. Guards the
// inject-via-alias contract so a portal with a divergent i18n can't silently break.
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import LangToggle from "@shared/components/LangToggle.vue";
import { lang, setLang } from "@/i18n";

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: "/", component: { template: "<div />" } }],
});
const mountToggle = (options = {}) =>
  mount(LangToggle, { ...options, global: { plugins: [router] } });

describe("LangToggle (shared)", () => {
  beforeEach(() => setLang("en"));

  it("renders two language options", () => {
    const w = mountToggle();
    const btns = w.findAll("button");
    expect(btns.length).toBe(2);
  });

  it("marks the active language via aria-pressed", () => {
    const w = mountToggle();
    const [en, ar] = w.findAll("button");
    expect(en.attributes("aria-pressed")).toBe("true");
    expect(ar.attributes("aria-pressed")).toBe("false");
  });

  it("flips the language when the other option is clicked", async () => {
    const w = mountToggle();
    const ar = w.findAll("button")[1];
    await ar.trigger("click");
    expect(lang.value).toBe("ar");
    expect(ar.attributes("aria-pressed")).toBe("true");
  });

  it("adds the header class for variant=header", () => {
    const w = mountToggle({ props: { variant: "header" } });
    expect(w.find(".lang-toggle").classes()).toContain("lang-toggle-header");
  });
});
