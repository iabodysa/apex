import { describe, expect, it } from "vitest";
import { createDraftStore, isCacheablePortalAsset } from "./offline.js";

class MemoryStorage {
  constructor() { this.values = new Map(); }
  get length() { return this.values.size; }
  key(index) { return [...this.values.keys()][index] ?? null; }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

describe("offline identity boundary", () => {
  it("namespaces drafts by site, entry, opaque subject, and form", () => {
    const storage = new MemoryStorage();
    const drafts = createDraftStore({
      storage,
      site: "apex.localhost",
      entry: "worker",
      subjectScope: "subject-a",
    });
    drafts.write("transport-request", { note: "saved" });

    expect(storage.getItem("apex:draft:apex.localhost:worker:subject-a:transport-request"))
      .toBe('{"note":"saved"}');
  });

  it("clears the prior subject drafts when identity changes", () => {
    const storage = new MemoryStorage();
    const oldDrafts = createDraftStore({
      storage, site: "apex.localhost", entry: "worker", subjectScope: "subject-a",
    });
    oldDrafts.activate();
    oldDrafts.write("request", { note: "private" });

    const nextDrafts = createDraftStore({
      storage, site: "apex.localhost", entry: "worker", subjectScope: "subject-b",
    });
    nextDrafts.activate();

    expect(oldDrafts.read("request")).toBeNull();
  });

  it("never classifies API responses or personalized HTML as cacheable", () => {
    expect(isCacheablePortalAsset({ url: "/api/method/apex.private", method: "GET", contentType: "application/json" }))
      .toBe(false);
    expect(isCacheablePortalAsset({ url: "/masar/", method: "GET", contentType: "text/html" }))
      .toBe(false);
    expect(isCacheablePortalAsset({ url: "/assets/apex/app.abc123.js", method: "GET", contentType: "text/javascript" }))
      .toBe(true);
  });

  it("rejects cross-origin assets even when their pathname resembles Apex", () => {
    expect(isCacheablePortalAsset({
      url: "https://attacker.example/assets/apex/app.abc123.js",
      origin: "https://apex.example",
      method: "GET",
      contentType: "text/javascript",
    })).toBe(false);
  });
});
