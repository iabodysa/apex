// [#t647-shared-call]
// call() is maintained once in frontend_shared/call.js (alias @shared).
// Re-exported here so existing consumers keep their `import { call } from './api'` import.
export { call } from "@shared/call";
