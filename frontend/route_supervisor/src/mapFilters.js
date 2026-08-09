// Copyright (c) 2026, afmcoltd

export const driverFilterValue = (row) => row.driver || row.driver_name || "";

export const matchesDriverFilter = (row, value) =>
  !value || row.driver === value || row.driver_name === value;

export function normalizeDriverFilter(rows, value) {
  if (!value) return "";
  const legacy = rows.find((row) => row.driver_name === value && row.driver);
  return legacy?.driver || value;
}

export function uniqueDriverOptions(rows) {
  const byDriver = new Map();
  for (const row of rows) {
    const value = driverFilterValue(row);
    if (value && !byDriver.has(value)) {
      byDriver.set(value, row.driver_name || row.driver || value);
    }
  }
  return [...byDriver.entries()]
    .sort((a, b) => a[1].localeCompare(b[1]))
    .map(([value, label]) => ({ label, value }));
}
