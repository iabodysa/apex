// Copyright (c) 2026, afmcoltd
import path from "path";
import { createPortalConfig } from "../frontend_shared/vite.base.js";

const merged = path.resolve(__dirname, "../housing/src");

const config = createPortalConfig({ dirname: __dirname, name: "safety_portal" });
config.resolve.alias["@"] = merged;
config.resolve.alias["@merged"] = merged;

export default config;
