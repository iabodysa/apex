import frappeUIPreset from "frappe-ui/tailwind";

export default {
  presets: [frappeUIPreset],
  content: [
    "./index.html",
    "./**/*.{vue,js,mjs,ts}",
    "../node_modules/frappe-ui/src/**/*.{vue,js,ts}",
  ],
};
