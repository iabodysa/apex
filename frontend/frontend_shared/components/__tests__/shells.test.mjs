// Copyright (c) 2026, AFMCO and contributors
// Guards the slot/prop contract of the three archetype shells so a Wave-1 portal
// can adopt them by muscle memory: each shell must render its named slots into the
// documented regions and expose the layout hooks the portals target.
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import {
  FleetPageShell,
  MobileConsoleShell,
  TabletSupervisorShell,
} from "@shared/components/index.js";

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: "/", component: { template: "<div />" } }],
});

const mountSupervisor = (options = {}) =>
  mount(TabletSupervisorShell, {
    ...options,
    global: { ...(options.global || {}), plugins: [router] },
  });

describe("FleetPageShell", () => {
  it("renders brand, nav, actions and default content", () => {
    const w = mount(FleetPageShell, {
      props: { title: "Hello", subtitle: "Sub" },
      slots: {
        brand: "<span class='b'>B</span>",
        nav: "<a class='n'>Home</a>",
        actions: "<span class='a'>A</span>",
        default: "<div class='content'>Body</div>",
      },
    });
    expect(w.find(".fleet-brand .b").exists()).toBe(true);
    expect(w.find(".fleet-nav .n").exists()).toBe(true);
    expect(w.find(".fleet-actions .a").exists()).toBe(true);
    expect(w.find(".fleet-body .content").exists()).toBe(true);
    expect(w.find(".fleet-hello").text()).toBe("Hello");
    expect(w.find(".fleet-sub").text()).toBe("Sub");
  });

  it("lets the heading slot override the title", () => {
    const w = mount(FleetPageShell, {
      props: { title: "Ignored" },
      slots: { heading: "<h2 class='custom'>Custom</h2>" },
    });
    expect(w.find(".custom").exists()).toBe(true);
    expect(w.find(".fleet-hello").exists()).toBe(false);
  });
});

describe("MobileConsoleShell", () => {
  it("renders the greeting, scroll content and bottom nav", () => {
    const w = mount(MobileConsoleShell, {
      props: { title: "Khalid", subtitle: "Morning" },
      slots: {
        default: "<div class='card'>Task</div>",
        nav: "<a class='is-active'>Home</a><a>Tasks</a><a>Me</a>",
      },
    });
    expect(w.find(".mc-greet b").text()).toBe("Khalid");
    expect(w.find(".mc-greet small").text()).toBe("Morning");
    expect(w.find(".mc-frame .card").exists()).toBe(true);
    expect(w.findAll(".mc-nav a").length).toBe(3);
  });

  it("hides the bottom nav when no nav slot is given", () => {
    const w = mount(MobileConsoleShell, { slots: { default: "x" } });
    expect(w.find(".mc-nav").exists()).toBe(false);
  });

  it("accepts the legacy width prop without turning it into a layout target", () => {
    const w = mount(MobileConsoleShell, { props: { maxWidth: 720 }, slots: { default: "x" } });
    expect(w.find(".mc-shell").attributes("style")).toBeUndefined();
    expect(w.find(".mc-frame").exists()).toBe(true);
  });
});

describe("TabletSupervisorShell", () => {
  it("renders side nav, top bar, KPI row and main content", () => {
    const w = mountSupervisor({
      props: { title: "Overview", subtitle: "Riyadh", accent: "#c0392b" },
      slots: {
        brand: "<b class='brand'>Apex</b>",
        nav: "<a class='is-active'>Board</a>",
        kpis: "<div class='kpi'>34</div>",
        default: "<table class='live'></table>",
      },
    });
    expect(w.find(".ts-brand .brand").exists()).toBe(true);
    expect(w.find(".ts-nav-list .is-active").exists()).toBe(true);
    expect(w.find(".ts-kpis .kpi").exists()).toBe(true);
    expect(w.find(".ts-scroll .live").exists()).toBe(true);
    expect(w.find(".ts-title h1").text()).toBe("Overview");
    // per-domain accent is injected as a CSS var on the root
    expect(w.find(".ts-shell").attributes("style")).toContain("#c0392b");
  });

  it("toggles the drawer via the menu button", async () => {
    const w = mountSupervisor({
      slots: { nav: "<a>Board</a>" },
    });
    expect(w.find(".ts-nav-open").exists()).toBe(false);
    await w.find(".ts-menu").trigger("click");
    expect(w.find(".ts-nav-open").exists()).toBe(true);
    expect(w.find(".ts-menu").attributes("aria-expanded")).toBe("true");
  });

  it("hides the KPI row when no kpis slot is given", () => {
    const w = mountSupervisor({ slots: { default: "x" } });
    expect(w.find(".ts-kpis").exists()).toBe(false);
  });

  // The side-nav look (padding, active tint, disabled and focus states) is written
  // with :slotted(), which compiles to a `<scopeId>-s` attribute the runtime stamps
  // on slot content. Route Supervisor supplies bare <button>s and relies entirely on
  // that stamp, so a regression here would silently unstyle the whole nav.
  it("stamps the slot scope id on nav items so :slotted rules reach them", () => {
    const w = mountSupervisor({
      slots: { nav: "<button class='item' disabled>Boarding</button>" },
    });
    const item = w.find(".ts-nav-list .item");
    expect(item.exists()).toBe(true);
    const slotScoped = Object.keys(item.attributes()).filter((a) => a.endsWith("-s"));
    expect(slotScoped.length).toBe(1);
    expect(slotScoped[0]).toBe(TabletSupervisorShell.__scopeId + "-s");
  });
});
