// Copyright (c) 2026, AFMCO and contributors
//
// Standalone generator for the two portal service workers. Renders each
// apex/www/<sw>.min.js from sw.template.js + sw.params.js. Both workers use the
// same deterministic hash of the complete emitted worker_portal asset tree.
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
import { completeAssetTreeBuildId } from "./sw.build-id.js";
import { SW_PARAMS } from "./sw.params.js";
import { renderServiceWorker } from "./sw.template.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const WWW_DIR = path.resolve(here, "../../apex/www");
const ASSET_TREE = path.resolve(here, "../../apex/public/worker_portal");

export function generate({ write } = {}) {
  let allOk = true;
  const build = completeAssetTreeBuildId(ASSET_TREE);
  for (const params of Object.values(SW_PARAMS)) {
    const swPath = path.join(WWW_DIR, params.swFilename);
    const existing = fs.existsSync(swPath) ? fs.readFileSync(swPath, "utf8") : "";
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
