import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The backend (FastAPI) defaults to :8080 (override with API_URL); proxy /api so the browser sees one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": process.env.API_URL ?? "http://localhost:8080" } },
});
