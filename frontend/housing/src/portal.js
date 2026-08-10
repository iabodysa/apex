// Copyright (c) 2026, afmcoltd
const bootData = (typeof window !== "undefined" && window.apex_portal) || {};

export const ENTRY = bootData.entry === "safety" ? "safety" : "housing";

const granted = new Set(Array.isArray(bootData.sections) ? bootData.sections : []);
const grants = bootData.can && typeof bootData.can === "object" ? bootData.can : {};

export function hasSection(id) {
  return granted.has(id);
}

export function can(action) {
  return grants[action] === true;
}

/* Write on the delivery is not the gate — each exit is held by its own role, so the server
   publishes the exits this caller may actually clear. Offering the button on write alone
   showed a large green control to someone the server would refuse after the tap. */
export function canClearExit(number) {
  const exits = Array.isArray(grants.exits) ? grants.exits : [];
  return exits.includes(Number(number));
}

export function grantedSections() {
  return [...granted];
}
