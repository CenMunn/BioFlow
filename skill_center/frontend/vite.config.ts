import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes("node_modules")) {
            if (/highlight|lowlight/.test(id)) return "highlight";
            if (
              /remark|rehype|markdown|unified|micromark|mdast|hast|unist|vfile|parse-entities|property-information/.test(
                id,
              )
            )
              return "markdown";
            return "vendor";
          }
        },
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:18120" } },
});
