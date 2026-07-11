// Copyright (c) 2026, AFMCO and contributors
import { createPortalConfig } from "../frontend_shared/vite.base.js";

// Masar Route Supervisor SPA — built to apex/public/route_supervisor_portal/, served at
// /assets/apex/route_supervisor_portal/ and hosted by www/masar-supervisor.html.
export default createPortalConfig({ dirname: __dirname, name: "route_supervisor_portal" });
