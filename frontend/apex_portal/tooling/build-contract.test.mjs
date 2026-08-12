import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";

const root = process.cwd();
const read = (name) => readFileSync(path.join(root, name), "utf8");

describe("inactive build contract", () => {
  it("runs from the root test chain without joining root workspaces", () => {
    const rootPackage = JSON.parse(readFileSync(path.join(root, "../package.json"), "utf8"));
    expect(rootPackage.workspaces).not.toContain("apex_portal");
    expect(rootPackage.scripts.test).toContain("npm test --prefix apex_portal");
  });

  it("has one HTML source, one mount call, one router creation, and one token entry", () => {
    expect(readdirSync(root).filter((name) => name === "index.html")).toEqual(["index.html"]);
    const main = read("main.js");
    expect(main.match(/\.mount\(/g)).toHaveLength(1);
    expect(main.match(/createPortalRouter\(/g)).toHaveLength(1);
    expect(main.match(/styles\/foundation\.css/g)).toHaveLength(1);
  });

  it("uses both shells and declares all seven domain feature slots without fake pages", () => {
    const app = read("App.vue");
    expect(app).toContain("MobileShell");
    expect(app).toContain("OperationsShell");
    const router = read("core/router.js");
    for (const feature of [
      "worker", "driver", "housing", "safety", "fleet-self-service",
      "fleet-operations", "transport-supervisor",
    ]) {
      expect(router).toContain(`\"${feature}\"`);
    }
    expect(readdirSync(root)).not.toContain("features");
  });

  it("does not import retired portal or frontend_shared source", () => {
    const source = ["main.js", "App.vue", "core/router.js", "shells/MobileShell.vue", "shells/OperationsShell.vue"]
      .map((name) => read(name))
      .join("\n");
    expect(source).not.toMatch(/frontend_shared|(?:^|\/)src\//);
    expect(source).not.toMatch(/node_modules\/frappe-ui|@frappe-ui-/);
    expect(source).toContain('from "frappe-ui"');
  });

  it("fails closed when verification mode is absent", () => {
    const result = spawnSync(
      process.execPath,
      ["../node_modules/vite/bin/vite.js", "build", "--config", "vite.config.js"],
      { cwd: root, encoding: "utf8", env: { ...process.env, APEX_PORTAL_REBUILD_VERIFY: "" } },
    );
    expect(result.status).not.toBe(0);
    expect(`${result.stdout}\n${result.stderr}`).toContain("APEX_PORTAL_REBUILD_VERIFY=1");
  });
});
