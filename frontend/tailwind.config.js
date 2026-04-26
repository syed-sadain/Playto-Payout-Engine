/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Syne", "system-ui", "sans-serif"],
        mono: ["DM Mono", "Courier New", "monospace"],
      },
    },
  },
  plugins: [],
};
