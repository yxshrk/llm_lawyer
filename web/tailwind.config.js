/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#fafaf9",
        ink: "#1c1917",
        muted: "#78716c",
        line: "#e7e5e4",
        accent: "#1d4ed8",
      },
    },
  },
  plugins: [],
};
