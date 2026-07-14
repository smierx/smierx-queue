import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Alles unter /api geht an die FastAPI, gleicher Pfad wie in Produktion.
// Im Docker-Compose zeigt VITE_API_TARGET auf den api-Container.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: process.env.VITE_API_TARGET ?? "http://localhost:8000" },
    },
  },
});
