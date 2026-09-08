import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 开发时前端直连 api 容器，避免 CORS 与硬编码地址
      "/api": { target: "http://api:8000", changeOrigin: true },
    },
  },
});
