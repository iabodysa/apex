// Copyright (c) 2026, afmcoltd

const VEHICLE = {
  available: { theme: "green", key: "statusShort.available" },
  assigned: { theme: "green", key: "statusShort.assigned" },
  workshop: { theme: "orange", key: "statusShort.workshop" },
  stopped: { theme: "gray", key: "statusShort.stopped" },
  stolen: { theme: "red", key: "statusShort.stolen" },
};

const TRIP = {
  planned: { theme: "orange", key: "emp.trips.planned" },
  inProgress: { theme: "blue", key: "emp.trips.inProgress" },
  completed: { theme: "green", key: "emp.trips.completed" },
};

const FUEL = {
  pending: { theme: "orange", key: "emp.fuel.status.pending" },
  approved: { theme: "blue", key: "emp.fuel.status.approved" },
  completed: { theme: "green", key: "emp.fuel.status.completed" },
  failed: { theme: "red", key: "emp.fuel.status.failed" },
  cancelled: { theme: "gray", key: "emp.fuel.status.cancelled" },
};

export const vehicleMeta = (status) => VEHICLE[status] || VEHICLE.available;
export const tripMeta = (status) => TRIP[status] || TRIP.planned;
export const fuelMeta = (statusKey) => FUEL[statusKey] || FUEL.pending;
