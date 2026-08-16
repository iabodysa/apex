import { describe, expect, it } from "vitest";
import { reactive } from "vue";
import { useResourceState } from "./useResourceState.js";

describe("shared resource state ladder", () => {
  it("reports loading first, even while an error and data both already sit on the resource", () => {
    const resource = reactive({ loading: true, error: new Error("stale failure"), data: { id: 1 } });
    const state = useResourceState(resource, () => false);

    expect(state.value).toBe("loading");
  });

  it("reports error once loading clears, ahead of the caller's own empty check", () => {
    const resource = reactive({ loading: false, error: new Error("network"), data: null });
    const state = useResourceState(resource, () => true);

    expect(state.value).toBe("error");
  });

  it("asks isEmpty only once loading and error are both clear", () => {
    const resource = reactive({ loading: false, error: null, data: [] });
    const state = useResourceState(resource, () => resource.data.length === 0);

    expect(state.value).toBe("empty");
  });

  it("reports ready when isEmpty says there is something to show", () => {
    const resource = reactive({ loading: false, error: null, data: [{ name: "ROW-1" }] });
    const state = useResourceState(resource, () => resource.data.length === 0);

    expect(state.value).toBe("ready");
  });

  it("never reports empty when the caller supplies no isEmpty", () => {
    const resource = reactive({ loading: false, error: null, data: null });
    const state = useResourceState(resource);

    expect(state.value).toBe("ready");
  });

  it("tracks the resource reactively as loading and error change", () => {
    const resource = reactive({ loading: true, error: null, data: null });
    const state = useResourceState(resource, () => !resource.data);

    expect(state.value).toBe("loading");

    resource.loading = false;
    expect(state.value).toBe("empty");

    resource.data = { id: 1 };
    expect(state.value).toBe("ready");

    resource.error = new Error("network");
    expect(state.value).toBe("error");
  });
});
