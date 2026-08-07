// Copyright (c) 2026, afmcoltd
import { createPortalConfig } from "../frontend_shared/vite.base.js";

export default createPortalConfig({
  dirname: __dirname,
  name: "worker_portal",
  serviceWorkers: ["driver_portal", "worker_portal"],
});
