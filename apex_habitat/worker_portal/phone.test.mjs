// Plain-node unit test for src/phone.js (no framework). Run: node phone.test.mjs
// Locks the hand-rolled worker-portal phone normaliser (T-164): +966, leading-0
// local, 00 international, non-Saudi, and non-digit separators must stay correct.
import { normalizeMsisdn } from "./src/phone.js";

const cases = [
  ["0512345678", "966512345678"],
  ["512345678", "966512345678"],
  ["+966512345678", "966512345678"],
  ["966512345678", "966512345678"],
  ["+966 51-234 5678", "966512345678"],
  ["00966512345678", "966512345678"],
  ["+49123456789", "49123456789"],
  ["0049123456789", "49123456789"],
  ["", ""],
  ["   ", ""],
  ["+966", "966"],
];

let failed = 0;
for (const [input, expected] of cases) {
  const got = normalizeMsisdn(input);
  if (got !== expected) {
    failed++;
    console.error(`FAIL  ${JSON.stringify(input)} -> ${JSON.stringify(got)} (want ${JSON.stringify(expected)})`);
  }
}
if (failed) {
  console.error(`${failed}/${cases.length} phone normaliser cases failed`);
  process.exit(1);
}
console.log(`phone normaliser: ${cases.length}/${cases.length} cases ok`);
