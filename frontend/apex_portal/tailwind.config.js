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
      // Every size in frappe-ui's scale carries positive tracking — 0.005em to 0.02em
      // (node_modules/frappe-ui/tailwind/plugin.js:78-211). Arabic is a connected script and
      // positive tracking breaks the joins, which the type contract forbids outright. A
      // `* { letter-spacing: 0 }` reset cannot fix it: a utility class (0,1,0) beats the
      // universal selector. The scale is therefore restated here at zero rather than the
      // emitted classes overridden, so the framework and the identity agree at the source.
      // `p-xs` also carries the identity's 13px floor; the preset ships it at 12px, which is
      // the size of every FormControl description a worker reads
      // (frappe-ui/src/components/FormControl/FormControl.vue:105-113).
      fontSize: {
        "2xs": ["11px", { lineHeight: "1.15", letterSpacing: "0", fontWeight: "420" }],
        xs: ["12px", { lineHeight: "1.15", letterSpacing: "0", fontWeight: "420" }],
        sm: ["13px", { lineHeight: "1.15", letterSpacing: "0", fontWeight: "420" }],
        base: ["14px", { lineHeight: "1.15", letterSpacing: "0", fontWeight: "420" }],
        lg: ["16px", { lineHeight: "1.15", letterSpacing: "0", fontWeight: "400" }],
        xl: ["18px", { lineHeight: "1.15", letterSpacing: "0", fontWeight: "400" }],
        "2xl": ["20px", { lineHeight: "1.15", letterSpacing: "0", fontWeight: "400" }],
        "3xl": ["24px", { lineHeight: "1.15", letterSpacing: "0", fontWeight: "400" }],
        "p-2xs": ["11px", { lineHeight: "1.6", letterSpacing: "0", fontWeight: "420" }],
        "p-xs": ["13px", { lineHeight: "1.6", letterSpacing: "0", fontWeight: "420" }],
        "p-sm": ["13px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "420" }],
        "p-base": ["14px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "420" }],
        "p-lg": ["16px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "400" }],
        "p-xl": ["18px", { lineHeight: "1.42", letterSpacing: "0", fontWeight: "400" }],
        "p-2xl": ["20px", { lineHeight: "1.38", letterSpacing: "0", fontWeight: "400" }],
        "p-3xl": ["24px", { lineHeight: "1.2", letterSpacing: "0", fontWeight: "400" }],
      },
    },
  },
  content: [
    "./index.html",
    "./**/*.{vue,js,mjs,ts}",
    "../node_modules/frappe-ui/src/**/*.{vue,js,ts}",
  ],
};
