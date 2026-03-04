import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

const INPUT = process.env.INPUT;
if (!INPUT) {
  throw new Error("INPUT environment variable is not set. Run: INPUT=mcp-app.html vite build");
}

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    rollupOptions: { input: INPUT },
    outDir: "dist",
    emptyOutDir: false,
    // Disable chunk size warning — Excalidraw bundle is large
    chunkSizeWarningLimit: 10000,
  },
  // Allow Excalidraw to import its assets
  optimizeDeps: {
    include: ["@excalidraw/excalidraw"],
  },
});
