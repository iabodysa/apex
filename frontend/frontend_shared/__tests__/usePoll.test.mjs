// Copyright (c) 2026, AFMCO and contributors
// The poll lifecycle is shared by two portals, so its contract is asserted once
// here rather than re-reasoned per portal. The pause-on-hide / refetch-on-refocus
// pair is the whole reason a portal must not hand-roll `setInterval`: a plain
// interval with an inline `!document.hidden` check inside the callback passes a
// casual reading but keeps the timer alive in a background tab AND leaves the
// operator looking at a snapshot up to one full interval old after they come back.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount } from "@vue/test-utils";
import { h } from "vue";
import { usePoll } from "@shared/usePoll.js";

let hidden = false;

// jsdom answers document.hidden from the prototype; shadow it with an own
// configurable property so a test can drive the visibility state directly.
function setHidden(value) {
  hidden = value;
  document.dispatchEvent(new Event("visibilitychange"));
}

// usePoll defers every refetch through Promise.resolve(), so a tick lands on the
// microtask queue rather than synchronously. Advancing the fake clock by 1ms is
// the smallest step that also drains those microtasks.
const flush = () => vi.advanceTimersByTimeAsync(1);

function poll(refetch, interval) {
  return mount({
    setup() {
      usePoll(refetch, interval);
      return () => h("div");
    },
  });
}

beforeEach(() => {
  hidden = false;
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => hidden,
  });
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  delete document.hidden;
});

describe("usePoll", () => {
  it("polls on the interval it is given and never on mount", async () => {
    const refetch = vi.fn(() => Promise.resolve());
    poll(refetch, 45000);

    // Mounting arms the timer; the first fetch is the caller's job, so that the
    // composable can be added to a portal that already loads on mount.
    expect(refetch).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(44999);
    expect(refetch).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("defaults to the 45s cadence both portals were already using", async () => {
    const refetch = vi.fn(() => Promise.resolve());
    poll(refetch);

    await vi.advanceTimersByTimeAsync(44999);
    expect(refetch).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("stops the interval while the tab is hidden and refetches on refocus", async () => {
    const refetch = vi.fn(() => Promise.resolve());
    poll(refetch, 45000);

    await vi.advanceTimersByTimeAsync(45000);
    expect(refetch).toHaveBeenCalledTimes(1);

    // Backgrounded: the timer is cleared, not merely short-circuited, so three
    // whole intervals pass in silence.
    setHidden(true);
    await vi.advanceTimersByTimeAsync(45000 * 3);
    expect(refetch).toHaveBeenCalledTimes(1);

    // Refocused: refetch immediately rather than after another full interval...
    setHidden(false);
    await flush();
    expect(refetch).toHaveBeenCalledTimes(2);

    // ...and the interval resumes from there.
    await vi.advanceTimersByTimeAsync(45000);
    expect(refetch).toHaveBeenCalledTimes(3);
  });

  it("never stacks a second fetch on an unsettled one", async () => {
    let settle;
    const refetch = vi.fn(() => new Promise((resolve) => (settle = resolve)));
    poll(refetch, 1000);

    await vi.advanceTimersByTimeAsync(1000);
    expect(refetch).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(3000);
    expect(refetch).toHaveBeenCalledTimes(1);

    settle();
    await vi.advanceTimersByTimeAsync(1000);
    expect(refetch).toHaveBeenCalledTimes(2);
  });

  it("keeps polling after a refetch rejects", async () => {
    const refetch = vi.fn(() => Promise.reject(new Error("offline")));
    poll(refetch, 1000);

    await vi.advanceTimersByTimeAsync(1000);
    expect(refetch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(refetch).toHaveBeenCalledTimes(2);
  });

  it("stops polling and stops listening once the component unmounts", async () => {
    const refetch = vi.fn(() => Promise.resolve());
    const wrapper = poll(refetch, 1000);

    await vi.advanceTimersByTimeAsync(1000);
    expect(refetch).toHaveBeenCalledTimes(1);

    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(5000);
    expect(refetch).toHaveBeenCalledTimes(1);

    // The visibilitychange handler is detached too, so a refocus after unmount
    // cannot resurrect the timer.
    setHidden(true);
    setHidden(false);
    await vi.advanceTimersByTimeAsync(5000);
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
