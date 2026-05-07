/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "bg-main": "#0c0c0e",
        "bg-sidebar": "#1a1a1a",
        "bg-card": "#161618",
        "border-default": "#2a2a2a",
        "brand-pink": "#ec4899",
        "brand-tertiary": "#52dea2",
      },
      fontFamily: {
        sans: ["Space Grotesk", "-apple-system", "PingFang SC", "sans-serif"],
      },
    },
  },
  plugins: [],
}
