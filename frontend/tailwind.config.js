/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Resolved through CSS custom properties so an admin-set brand colour
        // can override the whole scale at runtime (see docs/specs/customer-
        // branding.md). The defaults live in src/index.css and are the same
        // hexes this object used to carry, so an unbranded install is
        // unchanged.
        //
        // The variables MUST hold space-separated sRGB channels ("47 90 224"),
        // never a hex: Tailwind substitutes <alpha-value> into rgb(), so a hex
        // would emit `rgb(#2f5ae0 / 1)` — invalid CSS, which browsers drop
        // entirely. On .btn-primary the surviving `text-white` then gives you
        // an invisible white-on-white button. tests/test_branding_defaults_
        // unchanged.py pins the format for exactly that reason.
        brand: {
          50: "rgb(var(--brand-50) / <alpha-value>)",
          100: "rgb(var(--brand-100) / <alpha-value>)",
          200: "rgb(var(--brand-200) / <alpha-value>)",
          300: "rgb(var(--brand-300) / <alpha-value>)",
          400: "rgb(var(--brand-400) / <alpha-value>)",
          500: "rgb(var(--brand-500) / <alpha-value>)",
          600: "rgb(var(--brand-600) / <alpha-value>)",
          700: "rgb(var(--brand-700) / <alpha-value>)",
          800: "rgb(var(--brand-800) / <alpha-value>)",
          900: "rgb(var(--brand-900) / <alpha-value>)",
          950: "rgb(var(--brand-950) / <alpha-value>)",
        },
      },
    },
  },
  plugins: [],
};
