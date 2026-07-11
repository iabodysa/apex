// Copyright (c) 2026, AFMCO and contributors
//
// Standalone generator for the two portal service workers. Renders each
// apex/www/<sw>.min.js from sw.template.js + sw.params.js. The `build` hash is
// carried forward from the committed file (so a regen never disturbs the current
// bundle stamp) — the vite plugin is what advances it on a real build.
//
//   node frontend/frontend_shared/sw.generate.js          # --check (default): verify
//                                                          # committed bytes == render
//   node frontend/frontend_shared/sw.generate.js --write   # rewrite the two www files
//
// --check exits non-zero if any committed file is NOT byte-reconstructable, which
// is exactly the invariant the CI bundle-guard depends on.

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { SW_PARAMS } from "./sw.params.js";
import { renderServiceWorker } from "./sw.template.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const WWW_DIR = path.resolve(here, "../../apex/www");

// A placeholder build for a first-ever emit (no committed file yet). On a real
// build the vite plugin overwrites it with the true bundle hash.
const PLACEHOLDER_BUILD = "000000000000";

function currentBuild(src) {
  const m = src.match(/const BUILD = "([^"]*)";/);
  return m ? m[1] : PLACEHOLDER_BUILD;
}

export function generate({ write } = {}) {
  let allOk = true;
  for (const [name, params] of Object.entries(SW_PARAMS)) {
    const swPath = path.join(WWW_DIR, params.swFilename);
    const existing = fs.existsSync(swPath) ? fs.readFileSync(swPath, "utf8") : "";
    const build = currentBuild(existing);
    const rendered = renderServiceWorker({ ...params, build });

    if (write) {
      if (rendered !== existing) {
        fs.writeFileSync(swPath, rendered);
        console.log(`WROTE ${params.swFilename} (build ${build})`);
      } else {
        console.log(`SAME  ${params.swFilename} (build ${build}) — already up to date`);
      }
    } else {
      const ok = rendered === existing && existing !== "";
      allOk = allOk && ok;
      console.log(`${ok ? "OK  " : "FAIL"} ${params.swFilename} byte-reconstruction (build ${build})`);
    }
  }
  return allOk;
}

// Run only when invoked directly (not when imported by a test).
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const write = process.argv.includes("--write");
  const ok = generate({ write });
  if (!write && !ok) process.exit(1);
}
