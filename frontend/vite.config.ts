import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/v1": {
        target: "http://127.0.0.1:8000",
        ws: true,
        changeOrigin: false
      },
      "/auth": "http://127.0.0.1:8000",
      "/client": "http://127.0.0.1:8000",
      "/owner": "http://127.0.0.1:8000",
      "/notifications": "http://127.0.0.1:8000",
      "/workflow": "http://127.0.0.1:8000",
      "/marketplace": "http://127.0.0.1:8000",
      "/providers": "http://127.0.0.1:8000",
      "/addresses": "http://127.0.0.1:8000",
      "/applications": "http://127.0.0.1:8000",
      "/clients": "http://127.0.0.1:8000",
      "/registry": "http://127.0.0.1:8000",
      "/demo": "http://127.0.0.1:8000",
      "/document-templates": "http://127.0.0.1:8000",
      "/egrn-extracts": "http://127.0.0.1:8000",
      "/admin": "http://127.0.0.1:8000",
      "/address-photos": "http://127.0.0.1:8000"
    }
  }
});
