// Copyright (c) 2026, afmcoltd

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

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const write = process.argv.includes("--write");
  const ok = generate({ write });
  if (!write && !ok) process.exit(1);
}
