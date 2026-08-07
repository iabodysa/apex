// Copyright (c) 2026, AFMCO and contributors
//
// The status words the server actually uses, named once.
//
// FOUR vocabularies reach the portals and they overlap, so a bare string in a
// comparison cannot be judged by reading the line it sits on. `Completed` and
// `Cancelled` each belong to TWO of them, which is why
// `trip.trip_log_status === "Completed" || trip.status === "Completed"` was one
// expression asking two different questions with one word.
//
// Every member below is copied from the DocType's own Select options. When a member is
// added or renamed on the server, change it HERE and the whole portal set follows —
// statusVocabularies.test.mjs fails if these drift from the shipped JSON.

// apex/salis/doctype/dispatch_trip — the vehicle's journey.
export const TRIP = Object.freeze({
  PLANNED: "Planned",
  DISPATCHED: "Dispatched",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
});

// apex/salis/doctype/transport_request — the worker's request for a seat.
export const REQUEST = Object.freeze({
  NEW: "New",
  VALIDATED: "Validated",
  APPROVED: "Approved",
  SCHEDULED: "Scheduled",
  FULFILLED: "Fulfilled",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
});

// apex/salis/doctype/trip_boarding_state — one worker against one trip.
export const BOARDING = Object.freeze({
  PENDING: "Pending",
  WORKER_CLAIMED: "Worker Claimed",
  BOARDED: "Boarded",
  DRIVER_REJECTED: "Driver Rejected",
  ABSENT: "Absent",
});

// apex/salis/doctype/trip_start_log — the driver's own record of the run.
export const TRIP_LOG = Object.freeze({
  STARTED: "Started",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
});

// apex/salis/doctype/driver_attendance — whether the driver turned up at all.
// Shares the word Absent with BOARDING and means something entirely different: a
// driver who did not come to work, not a worker who did not board.
export const ATTENDANCE = Object.freeze({
  PRESENT: "Present",
  ABSENT: "Absent",
  LATE: "Late",
  ON_LEAVE: "On Leave",
});

// The order the worker's progress bar walks. Not every TRIP member: Cancelled is not a
// step forward, it ends the journey.
export const TRIP_PROGRESS_ORDER = Object.freeze([
  TRIP.PLANNED,
  TRIP.DISPATCHED,
  TRIP.COMPLETED,
]);

// A worker who has answered for themselves — no further prompt is owed.
export const BOARDING_SETTLED = Object.freeze([BOARDING.BOARDED, BOARDING.ABSENT]);

// A worker the driver could not take.
export const BOARDING_REFUSED = Object.freeze([BOARDING.ABSENT, BOARDING.DRIVER_REJECTED]);
