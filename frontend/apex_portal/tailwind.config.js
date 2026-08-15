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
      fontSize: {
        // `p-xs` is the size frappe-ui gives every FormControl description
        // (node_modules/frappe-ui/src/components/FormControl/FormControl.vue:105-113), and the
        // preset sets it to 12px with 0.02em tracking
        // (node_modules/frappe-ui/tailwind/plugin.js:155-162). The identity puts the floor at 13px
        // for anything a worker reads, and Thmanyah is a connected script that positive tracking
        // breaks. Restated through the preset's own scale, because overriding the emitted
        // `.text-p-xs` class instead would leave the framework and the identity disagreeing.
        "p-xs": ["13px", { lineHeight: "1.6", letterSpacing: "0", fontWeight: "420" }],
      },
    },
  },
  content: [
    "./index.html",
    "./**/*.{vue,js,mjs,ts}",
    "../node_modules/frappe-ui/src/**/*.{vue,js,ts}",
  ],
};
