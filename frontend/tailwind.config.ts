import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        blue: {
          50: "#EFF6FF",
          100: "#DBEAFE",
          300: "#93C5FD",
          600: "#2563EB",
          700: "#1D4ED8",
        },
      },
    },
  },
  plugins: [],
};
export default config;
