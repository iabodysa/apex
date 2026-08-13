import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const { draw, destroy, fetch } = vi.hoisted(() => ({
  draw: vi.fn().mockResolvedValue(undefined),
  destroy: vi.fn(),
  fetch: vi.fn(),
}));

vi.mock("frappe-ui", () => ({
  Button: { template: "<button><slot /></button>" },
  FormControl: { template: "<input />" },
  createResource: vi.fn(() => ({ fetch })),
}));

vi.mock("./leafletAdapter.js", () => ({
  createLeafletAdapter: () => ({ draw, destroy }),
}));

import TransportMapPage from "./TransportMapPage.vue";

describe("transport map selection", () => {
  beforeEach(() => {
    draw.mockClear();
    fetch.mockReset();
    fetch.mockResolvedValue({
      positions: [
        { dispatch_trip: "TRIP-1", project: "A", status: "Running", path: [[24.7, 46.7]] },
        { dispatch_trip: "TRIP-2", project: "B", status: "Waiting", path: [[21.5, 39.2]] },
      ],
    });
  });

  it("redraws and refits immediately when a visible trip is selected", async () => {
    const wrapper = mount(TransportMapPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    });
    await flushPromises();
    draw.mockClear();

    await wrapper.findAll(".transport-map-card")[1].trigger("click");
    await flushPromises();

    expect(draw).toHaveBeenCalledOnce();
    expect(draw.mock.calls[0][1]).toEqual([
      expect.objectContaining({ dispatch_trip: "TRIP-2" }),
    ]);
    wrapper.unmount();
  });
});
