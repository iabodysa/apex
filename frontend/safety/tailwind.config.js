// Copyright (c) 2026, afmcoltd
import frappeUIPreset from "frappe-ui/tailwind";

const FRAPPE_UI_SOURCES = "../node_modules/frappe-ui/src/" + "**/*.{vue,js,ts}";
const MERGED_SOURCES = "../housing/src/" + "**/*.{vue,js}";
const SHARED_COMPONENT_SOURCES = "../frontend_shared/components/" + "*.{vue,js}";

export default {
  presets: [frappeUIPreset],
  content: ["./index.html", MERGED_SOURCES, SHARED_COMPONENT_SOURCES, FRAPPE_UI_SOURCES],
  theme: {
    extend: {
      fontFamily: {
        sans: "var(--font)",
      },
      fontWeight: { semibold: "700" },
      borderRadius: { ah: "14px" },
    },
  },
  plugins: [],
};
