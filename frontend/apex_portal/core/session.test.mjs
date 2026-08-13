import { describe, expect, it } from "vitest";
import { parsePortalBootstrap, readPortalDocumentBootstrap } from "./session.js";

const valid = () => ({
  entry: "worker",
  public_path: "/masar/",
  initial_route: "/home",
  capabilities: ["worker.home", "worker.trip.read"],
  site_name: "apex.localhost",
  socketio_port: 9000,
  async_enabled: true,
  language: "ar",
  subject_scope: "subject_3f189c11",
});

describe("portal bootstrap", () => {
  it("reads non-executable JSON contracts from the generated document", () => {
    document.body.innerHTML = `
      <script id="apex-portal-bootstrap" type="application/json">${JSON.stringify(valid())}</script>
      <script id="apex-portal-shell" type="application/json">{"service_worker_url":"/worker.js"}</script>
      <script id="apex-csrf-token" type="application/json">"csrf-value"</script>
    `;

    expect(readPortalDocumentBootstrap(document)).toEqual({
      portal: valid(),
      shell: { service_worker_url: "/worker.js" },
      csrfToken: "csrf-value",
    });
  });

  it("rejects a missing or malformed document contract", () => {
    document.body.innerHTML = '<script id="apex-portal-bootstrap" type="application/json">{</script>';
    expect(() => readPortalDocumentBootstrap(document)).toThrow(/apex-portal-bootstrap/);
  });

  it("returns an immutable normalized contract", () => {
    const parsed = parsePortalBootstrap(valid());
    expect(parsed.entry).toBe("worker");
    expect(Object.isFrozen(parsed)).toBe(true);
    expect(Object.isFrozen(parsed.capabilities)).toBe(true);
  });

  it("rejects malformed capabilities", () => {
    expect(() => parsePortalBootstrap({ ...valid(), capabilities: "worker.home" }))
      .toThrow(/capabilities/);
    expect(() => parsePortalBootstrap({ ...valid(), capabilities: ["worker.home", 7] }))
      .toThrow(/capabilities/);
  });

  it.each(["token", "cookie", "password", "api_key", "user_id"])(
    "rejects a raw credential field named %s",
    (field) => {
      expect(() => parsePortalBootstrap({ ...valid(), [field]: "secret" }))
        .toThrow(/unexpected|credential/i);
    },
  );

  it("rejects unknown entries and mismatched public paths", () => {
    expect(() => parsePortalBootstrap({ ...valid(), entry: "admin" })).toThrow(/entry/);
    expect(() => parsePortalBootstrap({ ...valid(), public_path: "/driver/" }))
      .toThrow(/public_path/);
  });

  it("rejects a raw user identity as the draft subject scope", () => {
    expect(() => parsePortalBootstrap({ ...valid(), subject_scope: "worker@example.com" }))
      .toThrow(/subject_scope/);
  });
});
