/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          200: "#bcd3ff",
          300: "#8eb4fc",
          400: "#5c8bf8",
          500: "#3b6ef5",
          600: "#2f5ae0",
          700: "#2647b4",
          800: "#233f8f",
          900: "#1e3670",
          950: "#152245",
        },
      },
    },
  },
  plugins: [],
};
