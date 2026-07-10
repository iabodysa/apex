// Copyright (c) 2026, AFMCO and contributors
import { createPortalConfig } from "../frontend_shared/vite.base.js";

// [#euj6hi] [#2imxz2]
export default createPortalConfig({
  dirname: __dirname,
  name: "driver_portal",
  sw: "driver-sw.min.js",
});
