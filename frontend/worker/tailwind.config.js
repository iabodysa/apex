// Copyright (c) 2026, AFMCO and contributors
// No `colors` block. A Tailwind palette is a fourth copy of the brand that can
// never follow light/dark, because a utility class emits a literal. Colour reaches
// this portal through @shared/tokens.css only. The `ah` block that used to sit here
// carried a sand (#ECE6D6) and a danger (#C0392B) that both disagreed with the token
// file; no `ah-*` utility was referenced anywhere in worker/, driver/ or the shared
// components.
//
// `sans` resolves the shared --font instead of restating it: Tailwind's preflight
// sets font-family on <html> from this value, and the stack it held had dropped
// Cairo — so `font-sans` could never reach the Cairo family this portal self-hosts
// in src/index.css, and the document root and the body asked for different faces.
// Resolving the token also keeps the family order a single decision in tokens.css.
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
      fontFamily: {
        sans: "var(--font)",
      },
      borderRadius: { ah: "14px" },
    },
  },
  plugins: [],
};
