import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Built into web/dist and served by the local server (src/hoa_app), which fills in
// the per-launch API token in index.html. There is no separate dev server.
export default defineConfig({
  plugins: [react()],
  // one bundle is fine for an app served from this computer – no network to wait on
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false, chunkSizeWarningLimit: 1500 },
  test: {
    environment: "jsdom",
    globals: true,
    coverage: { provider: "v8", include: ["src/**/*.{ts,tsx}"], exclude: ["src/main.tsx"] },
  },
});
