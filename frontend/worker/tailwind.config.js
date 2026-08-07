// Copyright (c) 2026, afmcoltd
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js}",
    "../driver/src/**/*.{vue,js}",
    "../frontend_shared/**/*.{vue,js}",
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
