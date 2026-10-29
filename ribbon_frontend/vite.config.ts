import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: "../hsd_tool/static/ribbon",
    emptyOutDir: true,
    sourcemap: false,
    minify: true,
    lib: { entry: "src/embed.tsx", formats: ["es"], fileName: () => "ribbon.js" },
  },
});
