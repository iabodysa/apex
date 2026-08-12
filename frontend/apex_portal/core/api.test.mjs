import { describe, expect, it, vi } from "vitest";
import { createPortalCall } from "./api.js";

describe("portal API transport", () => {
  it("uses the frappe-ui request primitive and its CSRF path", async () => {
    const request = vi.fn().mockResolvedValue({ ready: true });
    const call = createPortalCall(request);

    await expect(call("apex.example.run", { name: "DEMO" })).resolves.toEqual({ ready: true });
    expect(request).toHaveBeenCalledWith({
      url: "apex.example.run",
      method: "POST",
      params: { name: "DEMO" },
    });
  });
});
