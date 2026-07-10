// Copyright (c) 2026, AFMCO and contributors
// Test-fixture stand-in for frappe-ui (aliased in vitest.config), so BuildingPicker
// can mount without the real resource layer. createListResource synchronously
// "resolves" with the rows the test set via __setRows, exposing the same shape the
// component reads (.data and .list.loading).
let ROWS = [];

export function __setRows(rows) {
  ROWS = rows;
}

export function createListResource(opts) {
  if (opts && typeof opts.onSuccess === "function") opts.onSuccess(ROWS);
  return { data: ROWS, list: { loading: false } };
}
