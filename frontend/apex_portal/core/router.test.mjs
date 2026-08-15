import { describe, expect, it } from "vitest";
import { createMemoryHistory } from "vue-router";
import {
  FEATURE_SLOTS,
  PORTAL_CONTEXTS,
  createPortalRouter,
  getPortalContext,
} from "./router.js";

const component = { template: "<p>ready</p>" };
const routes = [
  { path: "/home", name: "home", feature: "worker", capability: "worker.home", component },
  { path: "/requests", name: "requests", feature: "worker", capability: "worker.request.read", component },
  { path: "/requests/:name", name: "request-detail", feature: "worker", capability: "worker.request.read", component },
];

describe("portal registry", () => {
  it("contains six immutable contexts, seven paths, and seven feature slots", () => {
    expect(Object.keys(PORTAL_CONTEXTS)).toHaveLength(6);
    expect(Object.values(PORTAL_CONTEXTS).flatMap((item) => item.publicPaths)).toHaveLength(7);
    expect(FEATURE_SLOTS).toEqual([
      "worker",
      "driver",
      "housing",
      "safety",
      "fleet-self-service",
      "fleet-operations",
      "transport-supervisor",
    ]);
    expect(JSON.stringify(PORTAL_CONTEXTS)).not.toMatch(/role/i);
    expect(Object.isFrozen(getPortalContext("worker"))).toBe(true);
    expect(getPortalContext("housing").landing).toBe("/today");
  });
});

describe("portal router", () => {
  const makeRouter = (capabilities) => createPortalRouter({
    context: getPortalContext("worker"),
    capabilities,
    routes,
    history: createMemoryHistory(),
  });

  it("registers only capability-backed feature routes", () => {
    const router = makeRouter(["worker.home"]);
    expect(router.hasRoute("home")).toBe(true);
    expect(router.hasRoute("requests")).toBe(false);
  });

  it("preserves an authorized deep link", async () => {
    const router = makeRouter(["worker.home", "worker.request.read"]);
    await router.push("/requests");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("requests");
  });

  it("resolves an unauthorized deep link to the local denied view", async () => {
    const router = makeRouter(["worker.home"]);
    await router.push("/requests");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("access-denied");
  });

  // A record deep link is the one a shared tab and a pasted link actually carry. Matching it as a
  // string against "/requests/:name" silently sent the reader to the landing list, which reads as
  // "the record is not there" rather than "you may not open it".
  it("refuses an unauthorized deep link into a record instead of dropping it on the landing list", async () => {
    const router = makeRouter(["worker.home"]);
    await router.push("/requests/REQ-0001");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("access-denied");
    expect(router.currentRoute.value.query.from).toBe("/requests/REQ-0001");
  });

  it("redirects an unknown hash to the context landing", async () => {
    const router = makeRouter(["worker.home"]);
    await router.push("/unknown");
    await router.isReady();
    expect(router.currentRoute.value.path).toBe("/home");
  });

  it("uses a granted server-selected initial route", async () => {
    const router = createPortalRouter({
      context: getPortalContext("worker"),
      capabilities: ["worker.home", "worker.request.read"],
      routes,
      initialRoute: "/requests",
      history: createMemoryHistory(),
    });
    await router.push("/unknown");
    await router.isReady();
    expect(router.currentRoute.value.path).toBe("/requests");
  });
});
