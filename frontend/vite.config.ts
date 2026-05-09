import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://127.0.0.1:8000",
      "/marketplace": "http://127.0.0.1:8000",
      "/providers": "http://127.0.0.1:8000",
      "/addresses": "http://127.0.0.1:8000",
      "/applications": "http://127.0.0.1:8000",
      "/clients": "http://127.0.0.1:8000",
      "/registry": "http://127.0.0.1:8000",
      "/document-templates": "http://127.0.0.1:8000",
      "/egrn-extracts": "http://127.0.0.1:8000"
    }
  }
});
