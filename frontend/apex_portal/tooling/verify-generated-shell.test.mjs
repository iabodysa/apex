import { afterEach, describe, expect, it } from "vitest";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { verifyGeneratedShell } from "./verify-generated-shell.js";
import { SEALED_INDEX_HTML } from "./seal-public-index.js";

const roots = [];
afterEach(() => roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

function fixture({
  shellEntry = "assets/index-abc.js",
  outputEntry = "assets/index-abc.js",
  bootstrap = true,
  executableInline = false,
  publishedIndex = SEALED_INDEX_HTML,
} = {}) {
  const root = path.join(tmpdir(), `apex-shell-${crypto.randomUUID()}`);
  roots.push(root);
  const outDir = path.join(root, "out");
  const indexPath = path.join(root, "shell.html");
  mkdirSync(path.join(outDir, ".vite"), { recursive: true });
  mkdirSync(path.join(outDir, "assets"), { recursive: true });
  writeFileSync(path.join(outDir, ".vite/manifest.json"), JSON.stringify({
    "index.html": { file: outputEntry, isEntry: true, css: ["assets/index.css"] },
  }));
  writeFileSync(path.join(outDir, outputEntry), "ready");
  writeFileSync(path.join(outDir, "assets/index.css"), ".inline-flex{}.w-7{}.h-7{}");
  writeFileSync(path.join(outDir, "index.html"), publishedIndex);
  const contracts = bootstrap
    ? '<script id="apex-portal-bootstrap" type="application/json">{{ boot["apex_portal"] | tojson }}</script>'
      + '<script id="apex-portal-shell" type="application/json">{{ shell_meta | tojson }}</script>'
      + '<script id="apex-csrf-token" type="application/json">{{ csrf_token | tojson }}</script>'
    : "";
  const inline = executableInline ? "<script>window.portal = {};</script>" : "";
  writeFileSync(indexPath, `${contracts}${inline}<script type="module" src="/assets/apex/apex_portal/${shellEntry}"></script>`);
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

  it("rejects a missing JSON bootstrap contract", () => {
    expect(() => verifyGeneratedShell(fixture({ bootstrap: false })))
      .toThrow(/bootstrap contract/);
  });

  it("rejects executable inline scripts", () => {
    expect(() => verifyGeneratedShell(fixture({ executableInline: true })))
      .toThrow(/executable inline script/);
  });

  it("rejects a published index that still boots the SPA", () => {
    const publishedIndex = '<!doctype html><div id="app"></div>'
      + '<script type="module" src="/assets/apex/apex_portal/assets/index-abc.js"></script>';
    expect(() => verifyGeneratedShell(fixture({ publishedIndex })))
      .toThrow(/not the inert stub/);
  });

  it("keeps the stub free of Jinja, of a mount element and of any script", () => {
    for (const delimiter of ["{{", "}}", "{%", "%}", "{#", "#}"]) {
      expect(SEALED_INDEX_HTML).not.toContain(delimiter);
    }
    expect(SEALED_INDEX_HTML).not.toMatch(/<script\b|id\s*=\s*["']app["']|style\s*=/i);
  });
});
