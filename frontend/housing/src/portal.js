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

export function grantedSections() {
  return [...granted];
}
