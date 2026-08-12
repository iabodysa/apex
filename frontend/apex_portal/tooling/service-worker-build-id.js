// Copyright (c) 2026, Apex contributors
import crypto from "crypto";
import fs from "fs";
import path from "path";

function filesBelow(root, current = root) {
  return fs.readdirSync(current, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(current, entry.name);
    return entry.isDirectory() ? filesBelow(root, absolute) : [absolute];
  });
}

export function completeAssetTreeBuildId(root) {
  const hash = crypto.createHash("sha256");
  for (const absolute of filesBelow(root).sort()) {
    const relative = path.relative(root, absolute).split(path.sep).join("/");
    hash.update(relative);
    hash.update("\0");
    hash.update(fs.readFileSync(absolute));
    hash.update("\0");
  }
  return hash.digest("hex").slice(0, 12);
}
