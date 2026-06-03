export default {
  content: ["./enterprise.html", "./src/**/*.{js,jsx}", "./components/**/*.{js,jsx}", "./layouts/**/*.{js,jsx}", "./pages/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ats: {
          ink: "#18202f",
          muted: "#667085",
          line: "#d9e0ea",
          surface: "#f7f9fc",
          panel: "#ffffff",
          brand: "#2563eb",
          success: "#12805c",
          warning: "#b7791f",
          danger: "#b42318"
        }
      },
      boxShadow: {
        ats: "0 1px 2px rgba(16,24,40,.08), 0 8px 24px rgba(16,24,40,.06)"
      }
    }
  },
  plugins: []
};
