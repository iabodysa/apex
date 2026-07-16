// Copyright (c) 2026, AFMCO and contributors
import { createPortalConfig } from "../frontend_shared/vite.base.js";

// [#cynnk9] Backup of the Fleet OS supervisor board, preserved live at /fleet-os
// while the primary /fleet route becomes the employee page. Builds to
// apex/public/fleet_os_portal/ so it serves independently of fleet_portal.
export default createPortalConfig({ dirname: __dirname, name: "fleet_os_portal" });
