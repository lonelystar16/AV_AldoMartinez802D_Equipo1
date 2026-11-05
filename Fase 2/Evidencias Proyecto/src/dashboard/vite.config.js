import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo, /api va a la API local (uvicorn en 127.0.0.1:8000). En Docker
// lo resuelve nginx (docker/dashboard/nginx.conf) hacia el servicio api.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (ruta) => ruta.replace(/^\/api/, ""),
      },
    },
  },
});
