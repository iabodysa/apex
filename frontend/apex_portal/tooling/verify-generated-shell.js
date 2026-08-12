import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(portalRoot, "../..");
const verification = process.env.APEX_PORTAL_REBUILD_VERIFY === "1";
const outputRoot = verification
  ? process.env.APEX_PORTAL_VERIFY_OUT_DIR
  : path.resolve(repositoryRoot, "apex/public/apex_portal");
const shellPath = verification
  ? process.env.APEX_PORTAL_VERIFY_INDEX_PATH
  : path.resolve(repositoryRoot, "apex/templates/includes/apex_portal_app.html");

export function verifyGeneratedShell({ outDir = outputRoot, indexPath = shellPath } = {}) {
  if (!outDir || !path.isAbsolute(outDir) || !indexPath || !path.isAbsolute(indexPath)) {
    throw new Error("Generated shell verification requires absolute output and index paths");
  }
  const manifestPath = path.join(outDir, ".vite/manifest.json");
  for (const required of [manifestPath, indexPath]) {
    if (!existsSync(required)) throw new Error(`Missing generated portal artifact: ${required}`);
  }

  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const entry = manifest["index.html"];
  if (!entry?.isEntry || !entry.file) throw new Error("Vite manifest has no index.html entry");

  const shell = readFileSync(indexPath, "utf8");
  const expectedUrl = `/assets/apex/apex_portal/${entry.file}`;
  if (!shell.includes(expectedUrl)) {
    throw new Error(`Generated portal shell does not reference ${expectedUrl}`);
  }
  for (const file of [entry.file, ...(entry.css || [])]) {
    if (!existsSync(path.join(outDir, file))) {
      throw new Error(`Generated portal shell references missing output: ${file}`);
    }
  }
  if (!shell.includes("window.csrf_token") || !shell.includes('window["{{ key }}"]')) {
    throw new Error("Generated portal shell lost Frappe boot or CSRF contracts");
  }
  return { manifestPath, indexPath, entry: entry.file };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = verifyGeneratedShell();
  console.log(`Verified generated portal shell: ${result.entry}`);
}
