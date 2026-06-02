import { defineConfig } from "vite";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import react from "@vitejs/plugin-react";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
// Config is in configs/ inside .jac/client/, so go up one level to .jac/client/, then up two more to project root
const buildDir = path.resolve(__dirname, "..");
const projectRoot = path.resolve(__dirname, "../../..");

// Jac source mapper plugin - maps errors back to original .jac files
function jacSourceMapper() {
  const sourceMap = new Map(); // compiled path -> original jac path

  return {
    name: 'jac-source-mapper',
    enforce: 'pre',

    // Extract source mapping and chain per-file source maps
    transform(code, id) {
      if (id.includes('/compiled/') && id.endsWith('.js')) {
        const match = code.match(/^\/\* Source: (.+?) \*\//);
        if (match) {
          sourceMap.set(id, match[1]);
        }
        // Load per-file .map if it exists and return it so Vite chains it
        const mapPath = id + '.map';
        try {
          if (fs.existsSync(mapPath)) {
            const rawMap = JSON.parse(fs.readFileSync(mapPath, 'utf-8'));
            return { code, map: rawMap };
          }
        } catch (e) {}
      }
      return null;
    },

    // Enhance error messages with original source info
    buildEnd() {
      // Store source map for error reporting
      this._jacSourceMap = sourceMap;
    },

    // Handle resolve errors to show original source
    resolveId(source, importer) {
      if (importer && sourceMap.has(importer)) {
        const originalSource = sourceMap.get(importer);
        // Check for common issues like double slashes
        if (source.includes('//') && !source.startsWith('http')) {
          this.error({
            message: `Cannot resolve "${source}" - path contains invalid double slash. Check your import in the original Jac file.`,
            id: originalSource,
            loc: { line: 1, column: 0 }
          });
        }
      }
      return null;
    }
  };
}

/**
 * Vite configuration generated from config.json (in project root)
 * To customize, edit config.json instead of this file.
 */

export default defineConfig({
  base: "/",
  define: {

  },
  plugins: [
    jacSourceMapper(),
    react()
  ],
  root: buildDir, // base folder (.jac/client/) so vite can find node_modules
  envDir: projectRoot, // Load .env files from project root
    build: {
    sourcemap: true, // Enable source maps for better error messages

    rollupOptions: {
      input: path.resolve(buildDir, "compiled/_entry.js"), // your compiled entry file
      output: {
        entryFileNames: "client.[hash].js", // name of the final js file
        assetFileNames: (assetInfo) => assetInfo.name?.endsWith('.css') ? 'styles.css' : '[name].[ext]',
        sourcemapPathTransform: (relativeSourcePath) => {
          // Transform source map paths to point to original location
          return relativeSourcePath;
        },
      },
    },
    outDir: path.resolve(buildDir, "dist"), // final bundled output
    emptyOutDir: true,
  },
  publicDir: false,
  resolve: {
      alias: {
        "@jac/runtime": path.resolve(buildDir, "compiled/client_runtime.js"),
        "@jac-client/assets": path.resolve(buildDir, "compiled/assets"),
      },
      extensions: [".mjs", ".js", ".mts", ".ts", ".jsx", ".tsx", ".json"],

  },
});
