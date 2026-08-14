import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import MobileShell from "./MobileShell.vue";
import OperationsShell from "./OperationsShell.vue";

const routes = [
  { path: "/home", component: { template: "<p>home</p>" } },
  { path: "/requests", component: { template: "<p>requests</p>" } },
  { path: "/arrivals", component: { template: "<p>arrivals</p>" } },
];

async function mountShell(component, options = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push(options.path ?? "/home");
  await router.isReady();
  const wrapper = mount(component, {
    props: {
      title: "مهامي اليوم",
      navigation: [
        { label: "الرئيسية", to: "/home", icon: "lucide-home" },
        { label: "الطلبات", to: "/requests", icon: "lucide-file-text" },
        ...(options.navigation || []),
      ],
    },
    slots: {
      actions: "<button class='test-action'>تحديث</button>",
      default: "<p class='test-content'>المحتوى</p>",
    },
    global: { plugins: [router] },
  });
  return { wrapper, router };
}

describe.each([
  ["mobile", MobileShell],
  ["operations", OperationsShell],
])("%s shell", (_name, component) => {
  it("owns semantic header, main, navigation, skip link, and one h1", async () => {
    const { wrapper } = await mountShell(component);
    expect(wrapper.find("a.skip-link").attributes("href")).toBe("#portal-content");
    expect(wrapper.find("header").exists()).toBe(true);
    expect(wrapper.find("main#portal-content").exists()).toBe(true);
    expect(wrapper.find("nav[aria-label='التنقل الرئيسي']").exists()).toBe(true);
    expect(wrapper.findAll("h1")).toHaveLength(1);
    expect(wrapper.get("h1").text()).toBe("مهامي اليوم");
  });

  it("renders the server-filtered navigation with native lucide icons", async () => {
    const { wrapper } = await mountShell(component);
    expect(wrapper.findAll("nav a").map((link) => link.text())).toEqual(["الرئيسية", "الطلبات"]);
    expect(wrapper.text()).not.toContain("إدارة المستخدمين");
    const icons = wrapper.findAll("nav a .portal-nav-icon");
    expect(icons.map((icon) => icon.element.tagName)).toEqual(["SPAN", "SPAN"]);
    expect(icons[0].classes()).toContain("lucide-home");
    expect(icons[1].classes()).toContain("lucide-file-text");
    expect(icons.every((icon) => icon.attributes("aria-hidden") === "true")).toBe(true);
    expect(wrapper.find("nav svg").exists()).toBe(false);
  });

  it("marks the current route and keeps action and content slots separate", async () => {
    const { wrapper } = await mountShell(component, { path: "/requests" });
    const active = wrapper.findAll("nav a").filter((link) => link.attributes("aria-current") === "page");
    expect(active).toHaveLength(1);
    expect(active[0].text()).toBe("الطلبات");
    expect(wrapper.find("header .test-action").exists()).toBe(true);
    expect(wrapper.find("main .test-content").exists()).toBe(true);
  });
});

describe("mobile navigation", () => {
  it("keeps four primary destinations visible and places every remaining route under more", async () => {
    const navigation = [
      { label: "التنقل", to: "/transport", icon: "lucide-navigation" },
      { label: "السجل", to: "/history", icon: "lucide-clock" },
      { label: "السكن", to: "/housing", icon: "lucide-map-pin" },
      { label: "العهد", to: "/custody", icon: "lucide-briefcase" },
      { label: "الملف", to: "/profile", icon: "lucide-user" },
    ];
    const { wrapper } = await mountShell(MobileShell, { navigation });

    expect(wrapper.findAll(".mobile-shell__nav > .portal-nav-link")).toHaveLength(4);
    expect(wrapper.find(".mobile-shell__more").exists()).toBe(true);
    expect(wrapper.findAll(".mobile-shell__more-menu .portal-nav-link")).toHaveLength(3);
    expect(new Set(wrapper.findAll("nav a").map((link) => link.attributes("href")))).toEqual(
      new Set(["/home", "/requests", ...navigation.map((item) => item.to)]),
    );
  });
});

describe("operations identity", () => {
  it("uses the full-color mark on the light operations rail", async () => {
    const { wrapper } = await mountShell(OperationsShell);
    expect(wrapper.get(".operations-shell__brand img").attributes("src"))
      .toBe("/assets/apex/icons/brand/apex-mark.svg");
  });

  it("offers grouped mobile navigation instead of a horizontally scrolling route strip", async () => {
    const priorWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    const navigation = [
      { label: "مهام اليوم", to: "/today", icon: "lucide-home", group: "اليوم" },
      { label: "القادمون", to: "/arrivals", icon: "lucide-users", group: "السكن" },
      { label: "العهد", to: "/custody", icon: "lucide-briefcase", group: "العهد والجرد" },
    ];
    const { wrapper } = await mountShell(OperationsShell, { navigation });

    expect(wrapper.find(".operations-shell__mobile-nav").exists()).toBe(true);
    expect(wrapper.findAll(".operations-shell__mobile-group")).toHaveLength(4);
    expect(wrapper.find(".operations-shell__mobile-nav").text()).toContain("العهد والجرد");
    Object.defineProperty(window, "innerWidth", { configurable: true, value: priorWidth });
  });

  it.each([390, 834])("uses grouped navigation at %ipx and opens the active route group", async (width) => {
    const priorWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
    const { wrapper } = await mountShell(OperationsShell, {
      path: "/arrivals",
      navigation: [
        { label: "مهام اليوم", to: "/today", group: "اليوم" },
        { label: "القادمون", to: "/arrivals", group: "السكن" },
      ],
    });

    expect(wrapper.find(".operations-shell__mobile-nav").exists()).toBe(true);
    const activeGroup = wrapper.findAll(".operations-shell__mobile-group")
      .find((group) => group.text().includes("القادمون"));
    expect(activeGroup.attributes()).toHaveProperty("open");
    wrapper.unmount();
    Object.defineProperty(window, "innerWidth", { configurable: true, value: priorWidth });
  });

  it("returns to the full rail above the 834px tablet breakpoint", async () => {
    const priorWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 835 });
    const { wrapper } = await mountShell(OperationsShell);
    expect(wrapper.find(".operations-shell__mobile-nav").exists()).toBe(false);
    expect(wrapper.find(".operations-shell__nav").exists()).toBe(true);
    wrapper.unmount();
    Object.defineProperty(window, "innerWidth", { configurable: true, value: priorWidth });
  });
});
