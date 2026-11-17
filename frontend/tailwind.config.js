/** @type {import('tailwindcss').Config} */
// Design tokens: one brand colour (deep teal), zone colours ONLY for risk, 8px spacing rhythm, 12px radius.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#f0fdfa", 100: "#ccfbf1", 200: "#99f6e4", 400: "#2dd4bf", 500: "#14b8a6", 600: "#0d9488", 700: "#0f766e", 800: "#115e59", 900: "#134e4a" },
        zred: "#DC2626",
        zyellow: "#F59E0B",
        zgreen: "#16A34A",
      },
      fontFamily: { sans: ["Inter", "system-ui", "Segoe UI", "Roboto", "sans-serif"] },
      borderRadius: { card: "12px" },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 16px rgba(15, 23, 42, 0.06)",
        pop: "0 8px 32px rgba(15, 23, 42, 0.16)",
      },
    },
  },
  plugins: [],
};
