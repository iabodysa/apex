// Copyright (c) 2026, afmcoltd
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const WORKER = dirname(fileURLToPath(import.meta.url));
const DRIVER = join(WORKER, "../driver");
const read = (root, relativePath) => readFileSync(join(root, relativePath), "utf8");

const driverApp = read(DRIVER, "src/App.vue");
assert.match(driverApp, /<FrappeUIProvider>/);
assert.match(driverApp, /<MobileConsoleShell\s+v-else>/);
assert.doesNotMatch(driverApp, /<Toast\s*\/>/);
assert.equal(existsSync(join(DRIVER, "src/components/Toast.vue")), false);

const unlinked = read(DRIVER, "src/components/Unlinked.vue");
assert.doesNotMatch(unlinked, /\bBrand\b|\bLangToggle\b/);

const toastAdapter = read(DRIVER, "src/toast.js");
assert.match(toastAdapter, /import\s+\{\s*toast\s*\}\s+from\s+["']frappe-ui["']/);
assert.match(toastAdapter, /toast\.create\s*\(/);
assert.doesNotMatch(toastAdapter, /toast\.(?:success|error)\s*\(/);
assert.doesNotMatch(toastAdapter, /\bref\s*\(|\btoasts\b/);

const workerApp = read(WORKER, "src/App.vue");
assert.match(workerApp, /:route="scene\.action\.to"/);
assert.doesNotMatch(workerApp, /\buseRouter\b|router\.push/);

for (const [root, relativePath] of [
  [WORKER, "src/components/BoardingFlow.vue"],
  [DRIVER, "src/components/BoardingManifest.vue"],
  [DRIVER, "src/components/BoardingScanner.vue"],
]) {
  const source = read(root, relativePath);
  assert.match(source, /<Button\b/);
  assert.doesNotMatch(source, /<button\b/);
}

const rating = read(WORKER, "src/components/TripRating.vue");
assert.match(rating, /<Button\b/);
assert.match(rating, /<FormControl\b/);
assert.doesNotMatch(rating, /<textarea\b/);

console.log("Portal library-control contracts pass.");
