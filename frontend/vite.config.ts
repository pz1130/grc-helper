import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@designcodeio/threeui/style.css": path.resolve(__dirname, "src/shaders/threeui.css"),
      "@designcodeio/threeui": path.resolve(__dirname, "src/shaders/predictive-arc/PredictiveArcCollection.tsx"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发时前端直连 api 容器，避免 CORS 与硬编码地址
      "/api": { target: "http://api:8000", changeOrigin: true },
    },
  },
});
