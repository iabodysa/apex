import { describe, expect, it, vi } from "vitest";

import { createPortalUpdateController } from "../core/serviceWorker.js";

function worker(state) {
  const listeners = [];
  return {
    state,
    postMessage: vi.fn(),
    addEventListener: (_event, handler) => listeners.push(handler),
    settle(next) {
      this.state = next;
      listeners.forEach((handler) => handler());
    },
  };
}

function registration({ active = {}, waiting = null, installing = null } = {}) {
  const found = [];
  return {
    active,
    waiting,
    installing,
    addEventListener: (event, handler) => event === "updatefound" && found.push(handler),
    announce() {
      found.forEach((handler) => handler());
    },
  };
}

function container() {
  const changed = [];
  return {
    addEventListener: (event, handler) => event === "controllerchange" && changed.push(handler),
    change() {
      changed.forEach((handler) => handler());
    },
  };
}

describe("the portal update offer", () => {
  it("offers nothing until a second worker finishes installing", () => {
    const installing = worker("installing");
    const update = createPortalUpdateController({ container: container(), reload: vi.fn() });
    update.attach(registration({ installing }));
    expect(update.ready.value).toBe(false);
    installing.settle("installed");
    expect(update.ready.value).toBe(true);
  });

  it("stays silent on a first install, where no worker is being replaced", () => {
    const installing = worker("installing");
    const update = createPortalUpdateController({ container: container(), reload: vi.fn() });
    update.attach(registration({ active: null, installing }));
    installing.settle("installed");
    expect(update.ready.value).toBe(false);
  });

  it("offers a worker that was already waiting when the page opened", () => {
    const update = createPortalUpdateController({ container: container(), reload: vi.fn() });
    update.attach(registration({ waiting: worker("installed") }));
    expect(update.ready.value).toBe(true);
  });

  it("hands the waiting worker its release only when the driver asks for it", () => {
    const waiting = worker("installed");
    const update = createPortalUpdateController({ container: container(), reload: vi.fn() });
    update.attach(registration({ waiting }));
    expect(waiting.postMessage).not.toHaveBeenCalled();
    update.apply();
    expect(waiting.postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
    expect(update.busy.value).toBe(true);
  });

  it("reloads on the handover it asked for, and not on the one it did not", () => {
    const reload = vi.fn();
    const bus = container();
    const update = createPortalUpdateController({ container: bus, reload });
    update.attach(registration({ waiting: worker("installed") }));
    bus.change();
    expect(reload).not.toHaveBeenCalled();
    update.apply();
    bus.change();
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
