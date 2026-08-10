// Copyright (c) 2026, afmcoltd
import frappeUIPreset from "frappe-ui/tailwind";

/* The preset is what compiles frappe-ui's own classes; without it every control the library
   ships renders unstyled. It has to be imported from THIS file rather than from the Vite or
   PostCSS config: Tailwind loads its config through its own CJS loader, and the preset reaches
   for `tailwindcss/plugin` without an extension, which Node's ESM resolver refuses. */
const FRAPPE_UI_SOURCES = "../node_modules/frappe-ui/src/" + "**/*.{vue,js,ts}";
const PORTAL_SOURCES = "./src/" + "**/*.{vue,js}";
const SHARED_COMPONENT_SOURCES = "../frontend_shared/components/" + "*.{vue,js}";

export default {
  presets: [frappeUIPreset],
  content: ["./index.html", PORTAL_SOURCES, SHARED_COMPONENT_SOURCES, FRAPPE_UI_SOURCES],
  theme: {
    extend: {
      fontFamily: {
        sans: "var(--font)",
      },
      fontWeight: { semibold: "700" },
    },
  },
  plugins: [],
};
