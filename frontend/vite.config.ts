import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Alles unter /api geht an die FastAPI, Prefix wird abgeschnitten.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
