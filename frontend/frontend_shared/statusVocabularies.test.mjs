// Copyright (c) 2026, AFMCO and contributors
//
// A-391 — the named vocabularies must stay equal to the DocType Select options they
// were copied from. A constants file that silently drifts from the server is worse
// than the hand-typed strings it replaced, because it looks authoritative.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";

import {
  ATTENDANCE,
  BOARDING,
  BOARDING_REFUSED,
  BOARDING_SETTLED,
  REQUEST,
  TRIP,
  TRIP_LOG,
  TRIP_PROGRESS_ORDER,
} from "./statusVocabularies.js";

const APP = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "apex");

function selectOptions(relativePath, fieldname) {
  const doc = JSON.parse(readFileSync(join(APP, relativePath), "utf8"));
  const field = doc.fields.find((f) => f.fieldname === fieldname);
  assert.ok(field, `${relativePath} has no field ${fieldname}`);
  return field.options.split("\n").filter(Boolean);
}

const CASES = [
  ["Dispatch Trip", "salis/doctype/dispatch_trip/dispatch_trip.json", "status", TRIP],
  ["Transport Request", "salis/doctype/transport_request/transport_request.json", "status", REQUEST],
  ["Trip Boarding State", "salis/doctype/trip_boarding_state/trip_boarding_state.json", "status", BOARDING],
  ["Trip Start Log", "salis/doctype/trip_start_log/trip_start_log.json", "status", TRIP_LOG],
  ["Driver Attendance", "salis/doctype/driver_attendance/driver_attendance.json", "status", ATTENDANCE],
];

for (const [label, path, fieldname, vocabulary] of CASES) {
  test(`${label} vocabulary matches the shipped Select options`, () => {
    const shipped = selectOptions(path, fieldname);
    const named = Object.values(vocabulary);
    assert.deepEqual(
      [...named].sort(),
      [...shipped].sort(),
      `${label}: the named vocabulary has drifted from the DocType`,
    );
  });
}

test("the overlapping words are real, which is why a bare string is ambiguous", () => {
  // If these ever stop overlapping the ambiguity is gone and this file's reason with it.
  assert.equal(TRIP.COMPLETED, TRIP_LOG.COMPLETED);
  assert.equal(TRIP.CANCELLED, REQUEST.CANCELLED);
  assert.equal(TRIP.CANCELLED, TRIP_LOG.CANCELLED);
  // The one that reads most alike and means least alike: a driver who did not come to
  // work versus a worker who did not board.
  assert.equal(ATTENDANCE.ABSENT, BOARDING.ABSENT);
});

test("derived sets are drawn from members, never re-typed", () => {
  for (const value of TRIP_PROGRESS_ORDER) {
    assert.ok(Object.values(TRIP).includes(value));
  }
  assert.ok(!TRIP_PROGRESS_ORDER.includes(TRIP.CANCELLED), "cancelled is not a step forward");
  for (const value of [...BOARDING_SETTLED, ...BOARDING_REFUSED]) {
    assert.ok(Object.values(BOARDING).includes(value));
  }
});

test("the vocabularies are frozen so a caller cannot edit them at runtime", () => {
  assert.throws(() => {
    TRIP.PLANNED = "x";
  }, TypeError);
});
