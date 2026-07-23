// Copyright (c) 2026, AFMCO and contributors
import { createPortalConfig } from "../frontend_shared/vite.base.js";

// [#mgc049]
export default createPortalConfig({
  dirname: __dirname,
  name: "worker_portal",
  serviceWorkers: ["driver_portal", "worker_portal"],
});
