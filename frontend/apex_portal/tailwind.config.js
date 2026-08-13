import frappeUIPreset from "frappe-ui/tailwind";

export default {
  presets: [frappeUIPreset],
  theme: {
    extend: {
      colors: {
        green: {
          700: "#006f41",
          800: "#005936",
        },
      },
    },
  },
  content: [
    "./index.html",
    "./**/*.{vue,js,mjs,ts}",
    "../node_modules/frappe-ui/src/**/*.{vue,js,ts}",
  ],
};
