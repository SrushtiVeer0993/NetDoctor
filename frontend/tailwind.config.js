/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#0b0e14",
        panel: "#11151d",
        panel2: "#161b25",
        border: "#232a37",
        healthy: "#22c55e",
        warning: "#eab308",
        critical: "#ef4444",
        info: "#3b82f6",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui"],
      },
    },
  },
  plugins: [],
};
