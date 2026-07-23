// Copyright (c) 2026, AFMCO and contributors
// [#t647-shared-call]
// fleet_portal's call() now lives in the cross-portal @shared/call layer (built
// on frappe-ui's frappeRequest). Re-exported here so every existing
// `import { call } from "./api.js"` call site keeps working unchanged.
export { call } from "@shared/call";
