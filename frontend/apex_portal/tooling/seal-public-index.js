import { writeFileSync } from "node:fs";
import path from "node:path";

// frappe-ui's buildConfig plugin COPIES outDir/index.html to the Jinja shell and leaves
// the original behind. apex/public/ is served by werkzeug's SharedDataMiddleware with no
// session and no role check, so that leftover is both a public copy of an unrendered
// template and a second SPA mount point beside the permission-checked www route.
// The build overwrites it with this inert stub once the real shell has been copied out.
export const SEALED_INDEX_HTML = `<!doctype html>
<html lang="ar" dir="rtl">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="robots" content="noindex, nofollow" />
    <meta name="referrer" content="no-referrer" />
    <title>Apex</title>
  </head>
  <body>
    <p>افتح أبكس من رابط البوابة الخاص بك.</p>
    <p lang="en" dir="ltr">Open Apex from your portal link.</p>
  </body>
</html>
`;

export function sealPublicIndex({ outDir } = {}) {
  if (!outDir || !path.isAbsolute(outDir)) {
    throw new Error("sealPublicIndex requires an absolute output directory");
  }
  return {
    name: "apex-seal-public-index",
    enforce: "post",
    apply: "build",
    closeBundle() {
      writeFileSync(path.join(outDir, "index.html"), SEALED_INDEX_HTML, "utf8");
    },
  };
}
