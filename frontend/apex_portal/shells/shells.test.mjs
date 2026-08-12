import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import MobileShell from "./MobileShell.vue";
import OperationsShell from "./OperationsShell.vue";

const routes = [
  { path: "/home", component: { template: "<p>home</p>" } },
  { path: "/requests", component: { template: "<p>requests</p>" } },
];

async function mountShell(component, options = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push(options.path ?? "/home");
  await router.isReady();
  const wrapper = mount(component, {
    props: {
      title: "مهامي اليوم",
      navigation: [
        { label: "الرئيسية", to: "/home", icon: "home" },
        { label: "الطلبات", to: "/requests", icon: "file-text" },
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

  it("renders only the server-filtered navigation supplied by its parent", async () => {
    const { wrapper } = await mountShell(component);
    expect(wrapper.findAll("nav a").map((link) => link.text())).toEqual(["الرئيسية", "الطلبات"]);
    expect(wrapper.text()).not.toContain("إدارة المستخدمين");
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
