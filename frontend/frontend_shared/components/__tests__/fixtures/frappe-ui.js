// Copyright (c) 2026, afmcoltd
let ROWS = [];

export function __setRows(rows) {
  ROWS = rows;
}

export function createListResource(opts) {
  if (opts && typeof opts.onSuccess === "function") opts.onSuccess(ROWS);
  return { data: ROWS, list: { loading: false } };
}
