// Copyright (c) 2026, AFMCO and contributors
export default {
  // The merged Masar portal builds BOTH holder types from this one host, so Tailwind
  // must scan the driver screens and the shared components too — otherwise driver-only
  // utility classes would be purged and the driver screens would render unstyled.
  content: [
    "./index.html",
    "./src/**/*.{vue,js}",
    "../driver/src/**/*.{vue,js}",
    "../frontend_shared/**/*.{vue,js}",
    // Never scan an installed dependency tree: a stray frontend_shared/node_modules
    // (gitignored, absent in CI) would otherwise inject env-specific utilities and
    // make the committed bundle non-reproducible across a local vs CI build.
    "!../frontend_shared/node_modules/**",
  ],
  theme: {
    extend: {
      colors: {
        ah: {
          primary: "#00844E",
          forest: "#072B1A",
          accent: "#60D297",
          sand: "#ECE6D6",
          surface: "#F8F5EE",
          warning: "#C9851F",
          danger: "#C0392B",
        },
      },
      fontFamily: {
        sans: ["Montserrat", "system-ui", "sans-serif"],
      },
      borderRadius: { ah: "14px" },
    },
  },
  plugins: [],
};
