// Copyright (c) 2026, AFMCO and contributors
// [#t647-shared-call]
// The single API-call layer shared by every *_portal SPA, built on frappe-ui's
// frappeRequest (CSRF is signed from window.csrf_token, exposed by the www host
// page). Each portal imports from "@shared/call":
//   - configureApi()  → wire frappeRequest as the resourceFetcher (call once in
//     main.js so createResource() throughout the app signs its requests).
//   - call(method,{args,type}) → imperative one-off method call, returning the
//     endpoint's unwrapped `message`. Used where a portal needs a direct call
//     outside a createResource (fleet_portal/api.js, driver_portal push opt-in).
import { frappeRequest, setConfig } from "frappe-ui";

// Wire frappe-ui's createResource() to sign every request via frappeRequest.
// Idempotent — safe to call once per SPA boot.
export function configureApi() {
  setConfig("resourceFetcher", frappeRequest);
}

// call(method, { args, type }) -> the endpoint's `message`.
//   GET  -> args become query params
//   POST/PUT/DELETE -> args become the JSON body
export function call(method, { args = null, type = "GET" } = {}) {
  const opts = { url: "/api/method/" + method, method: type };
  // frappeRequest carries `params` as the query-string for GET and as the JSON
  // body for POST/PUT/DELETE (the same split the old hand-rolled helper did).
  if (args) opts.params = args;
  // Resolves to the unwrapped `message` and rejects with a frappe-ui error.
  return frappeRequest(opts);
}
