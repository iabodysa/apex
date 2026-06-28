// [#t647-shared-call]
// call() is maintained once in frontend_shared/call.js (alias @shared).
// Re-exported here so existing consumers keep their `import { call } from './api'` import.
// (Context note kept from original: createResource handles round endpoints;
// this helper is used for the building picker's standard get_list call.)
export { call } from "@shared/call";
