// Copyright (c) 2026, AFMCO and contributors
// No `colors` block. A Tailwind palette is a fourth copy of the brand that can
// never follow light/dark, because a utility class emits a literal. Colour reaches
// this portal through @shared/tokens.css only. The `ah` block that used to sit here
// held the pre-correction warning and danger hues and a sand that disagreed with the
// token file; nothing in src/ ever referenced it.
//
// `sans` resolves the shared --font instead of restating it: Tailwind's preflight
// sets font-family on <html> from this value, and the stack it held had dropped
// Cairo, so the document root and the body were asking for different faces.
export default {
  content: ["./index.html", "./src/**/*.{vue,js}"],
  theme: {
    extend: {
      fontFamily: {
        sans: "var(--font)",
      },
      borderRadius: { ah: "14px" },
    },
  },
  plugins: [],
};
