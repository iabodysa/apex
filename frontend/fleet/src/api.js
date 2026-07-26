// Copyright (c) 2026, AFMCO and contributors
// [#t647-shared-call]
// This portal's call() now lives in the cross-portal @shared/call layer (built
// on frappe-ui's frappeRequest). Re-exported here so every existing
// `import { call } from "./api.js"` call site keeps working unchanged.
//
// [#a281] Byte-identical to fleet_os/src/api.js ON PURPOSE. There is no duplicated
// LOGIC left to share — the implementation is already single-sourced in
// @shared/call.js and this is a one-line re-export. Collapsing the two files would
// not remove an implementation, only a module specifier, and would cost five
// call-site rewrites (one here, four inside fleet_os, the preserved-verbatim
// rollback copy of the supervisor board) to delete one line of code.
export { call } from "@shared/call";
