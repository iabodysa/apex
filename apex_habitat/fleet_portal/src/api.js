// Copyright (c) 2026, AFMCO and contributors
// [#t647-shared-call]
// call() for fleet_portal, now built on frappe-ui's frappeRequest instead of a
// bespoke hand-rolled fetch (CSRF is handled by frappeRequest, configured via
// setConfig in main.js). The signature and return are unchanged so every existing
// call site keeps working: call(method, { args, type }) -> the endpoint's `message`.
//   GET  -> args become query params
//   POST/PUT/DELETE -> args become the JSON body
import { frappeRequest } from "frappe-ui";

export function call(method, { args = null, type = "GET" } = {}) {
  const opts = { url: "/api/method/" + method, method: type };
  // frappeRequest carries `params` as the query-string for GET and as the JSON
  // body for POST/PUT/DELETE (same split the old hand-rolled helper did).
  if (args) opts.params = args;
  // Resolves to the unwrapped `message` (same value the old helper returned via
  // `data.message`) and rejects with a frappe-ui error on failure.
  return frappeRequest(opts);
}
