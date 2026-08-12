import { afterEach, describe, expect, it } from "vitest";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { verifyGeneratedShell } from "./verify-generated-shell.js";

const roots = [];
afterEach(() => roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

function fixture({ shellEntry = "assets/index-abc.js", outputEntry = "assets/index-abc.js" } = {}) {
  const root = path.join(tmpdir(), `apex-shell-${crypto.randomUUID()}`);
  roots.push(root);
  const outDir = path.join(root, "out");
  const indexPath = path.join(root, "shell.html");
  mkdirSync(path.join(outDir, ".vite"), { recursive: true });
  mkdirSync(path.join(outDir, "assets"), { recursive: true });
  writeFileSync(path.join(outDir, ".vite/manifest.json"), JSON.stringify({
    "index.html": { file: outputEntry, isEntry: true },
  }));
  writeFileSync(path.join(outDir, outputEntry), "ready");
  writeFileSync(indexPath, `<script>window.csrf_token = 1; window["{{ key }}"] = 1;</script><script src="/assets/apex/apex_portal/${shellEntry}"></script>`);
  return { outDir, indexPath };
}

describe("generated portal shell verifier", () => {
  it("accepts a same-build manifest and shell", () => {
    expect(verifyGeneratedShell(fixture()).entry).toBe("assets/index-abc.js");
  });

  it("rejects a stale hashed reference", () => {
    expect(() => verifyGeneratedShell(fixture({ shellEntry: "assets/index-old.js" })))
      .toThrow(/does not reference/);
  });
});
