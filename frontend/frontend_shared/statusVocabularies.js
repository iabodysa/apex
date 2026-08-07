// Copyright (c) 2026, afmcoltd

export const TRIP = Object.freeze({
  PLANNED: "Planned",
  DISPATCHED: "Dispatched",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
});

export const REQUEST = Object.freeze({
  NEW: "New",
  VALIDATED: "Validated",
  APPROVED: "Approved",
  SCHEDULED: "Scheduled",
  FULFILLED: "Fulfilled",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
});

export const BOARDING = Object.freeze({
  PENDING: "Pending",
  WORKER_CLAIMED: "Worker Claimed",
  BOARDED: "Boarded",
  DRIVER_REJECTED: "Driver Rejected",
  ABSENT: "Absent",
});

export const TRIP_LOG = Object.freeze({
  STARTED: "Started",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
});

export const ATTENDANCE = Object.freeze({
  PRESENT: "Present",
  ABSENT: "Absent",
  LATE: "Late",
  ON_LEAVE: "On Leave",
});

export const TRIP_PROGRESS_ORDER = Object.freeze([
  TRIP.PLANNED,
  TRIP.DISPATCHED,
  TRIP.COMPLETED,
]);

export const BOARDING_SETTLED = Object.freeze([BOARDING.BOARDED, BOARDING.ABSENT]);

export const BOARDING_REFUSED = Object.freeze([BOARDING.ABSENT, BOARDING.DRIVER_REJECTED]);
