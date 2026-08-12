import { afterEach, describe, expect, it } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import App from "./App.vue";
import { getPortalContext } from "./core/router.js";

const routes = [{ path: "/", component: { template: "<p class='route-page'>جاهز</p>" } }];

async function mountApp(entry) {
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(App, {
    props: {
      context: getPortalContext(entry),
      title: "لوحة اليوم",
      navigation: [{ label: "الرئيسية", to: "/", icon: "home" }],
    },
    global: { plugins: [router] },
  });
  await flushPromises();
  return wrapper;
}

describe("clean portal application", () => {
  let wrapper;
  afterEach(() => wrapper?.unmount());

  it("selects the mobile shell for a personal context", async () => {
    wrapper = await mountApp("worker");
    expect(wrapper.find(".mobile-shell").exists()).toBe(true);
    expect(wrapper.find(".operations-shell").exists()).toBe(false);
    expect(wrapper.find(".route-page").text()).toBe("جاهز");
  });

  it("selects the operations shell for a supervisor context", async () => {
    wrapper = await mountApp("housing");
    expect(wrapper.find(".operations-shell").exists()).toBe(true);
    expect(wrapper.find(".mobile-shell").exists()).toBe(false);
  });
});
