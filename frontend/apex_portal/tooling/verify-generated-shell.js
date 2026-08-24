import { existsSync, readFileSync, writeFileSync } from "node:fs";
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

const JSON_BOOT_CONTRACTS = Object.freeze([
  ["apex-portal-bootstrap", '{{ boot["apex_portal"] | tojson }}'],
  ["apex-portal-shell", "{{ shell_meta | tojson }}"],
  ["apex-csrf-token", "{{ csrf_token | tojson }}"],
]);

function assertNonExecutableBootstrap(shell) {
  for (const [id, payload] of JSON_BOOT_CONTRACTS) {
    const pattern = new RegExp(
      `<script\\b(?=[^>]*\\bid=["']${id}["'])(?=[^>]*\\btype=["']application/json["'])[^>]*>[\\s\\S]*?<\\/script>`,
      "i",
    );
    const tag = shell.match(pattern)?.[0];
    if (!tag || !tag.includes(payload)) {
      throw new Error(`Generated portal shell lost JSON bootstrap contract: ${id}`);
    }
  }
  for (const match of shell.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    const attributes = match[1];
    if (/\btype=["']application\/json["']/i.test(attributes)) continue;
    if (!/\bsrc\s*=/i.test(attributes)) {
      throw new Error("Generated portal shell contains an executable inline script");
    }
  }
}

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
  const entryCss = (entry.css || [])
    .map((file) => readFileSync(path.join(outDir, file), "utf8"))
    .join("\n");
  for (const utility of [".inline-flex", ".w-7", ".h-7"]) {
    if (!entryCss.includes(utility)) {
      throw new Error(`Generated portal CSS is missing frappe-ui utility: ${utility}`);
    }
  }
  assertNonExecutableBootstrap(shell);
  const publishedIndex = path.join(outDir, "index.html");
  if (existsSync(publishedIndex)) {
    throw new Error(`Portal index left in the session-free asset path: ${publishedIndex}`);
  }
  return { manifestPath, indexPath, entry: entry.file };
}

export function normalizeGeneratedShell(html) {
  return html
    .replace(/^[ \t]+$/gm, "")
    .replace(/^ {10}<script>/gm, "    <script>")
    .replace(/^ {14}({%|window)/gm, "      $1")
    .replace(/^ {10}<\/script>/gm, "    </script>")
    .replace(/^ {10}<\/body>/gm, "  </body>")
    .replace(/^ {10}<\/html>/gm, "</html>")
    .replace(/\n{3,}/g, "\n\n");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(shellPath, normalizeGeneratedShell(readFileSync(shellPath, "utf8")));
  const result = verifyGeneratedShell();
  console.log(`Verified generated portal shell: ${result.entry}`);
}
