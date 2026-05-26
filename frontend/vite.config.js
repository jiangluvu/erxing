import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const buildTime = Date.now();

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:5000",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        entryFileNames: `assets/[name]-${buildTime}-[hash].js`,
        chunkFileNames: `assets/[name]-${buildTime}-[hash].js`,
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name.split('.');
          const ext = info[info.length - 1];
          if (/\.(png|jpe?g|gif|svg|webp|ico)$/i.test(assetInfo.name)) {
            return `assets/[name]-${buildTime}[extname]`;
          }
          return `assets/[name]-${buildTime}[extname]`;
        },
      },
    },
  },
});
