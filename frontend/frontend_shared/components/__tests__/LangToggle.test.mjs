// Copyright (c) 2026, AFMCO and contributors
// The shared LangToggle (driver/housing/safety) reads i18n through the `@/i18n`
// alias — here the test fixture — and flips the language on click. Guards the
// inject-via-alias contract so a portal with a divergent i18n can't silently break.
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import LangToggle from "@shared/components/LangToggle.vue";
import { lang, setLang } from "@/i18n";

describe("LangToggle (shared)", () => {
  beforeEach(() => setLang("en"));

  it("renders two language options", () => {
    const w = mount(LangToggle);
    const btns = w.findAll("button");
    expect(btns.length).toBe(2);
  });

  it("marks the active language via aria-pressed", () => {
    const w = mount(LangToggle);
    const [en, ar] = w.findAll("button");
    expect(en.attributes("aria-pressed")).toBe("true");
    expect(ar.attributes("aria-pressed")).toBe("false");
  });

  it("flips the language when the other option is clicked", async () => {
    const w = mount(LangToggle);
    const ar = w.findAll("button")[1];
    await ar.trigger("click");
    expect(lang.value).toBe("ar");
    expect(ar.attributes("aria-pressed")).toBe("true");
  });

  it("adds the header class for variant=header", () => {
    const w = mount(LangToggle, { props: { variant: "header" } });
    expect(w.find(".lang-toggle").classes()).toContain("lang-toggle-header");
  });
});
