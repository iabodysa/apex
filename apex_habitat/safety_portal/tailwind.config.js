export default {
  content: ["./index.html", "./src/**/*.{vue,js}"],
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
