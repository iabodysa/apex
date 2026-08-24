import { rmSync } from "node:fs";
import path from "node:path";

export function dropPublicIndex({ outDir } = {}) {
  if (!outDir || !path.isAbsolute(outDir)) {
    throw new Error("dropPublicIndex requires an absolute output directory");
  }
  return {
    name: "apex-drop-public-index",
    enforce: "post",
    apply: "build",
    closeBundle() {
      rmSync(path.join(outDir, "index.html"), { force: true });
    },
  };
}
