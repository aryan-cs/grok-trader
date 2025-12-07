import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import { copyFileSync, mkdirSync } from 'fs';

// Plugin to copy static files to dist
function copyStaticFiles() {
  return {
    name: 'copy-static-files',
    closeBundle() {
      const filesToCopy = [
        { src: 'manifest.json', dest: 'dist/manifest.json' },
        { src: 'public/sidebar.html', dest: 'dist/sidebar.html' },
        { src: 'src/content.css', dest: 'dist/content.css' },
      ];

      filesToCopy.forEach(({ src, dest }) => {
        try {
          copyFileSync(src, dest);
        } catch (err) {
          console.error(`Failed to copy ${src} to ${dest}:`, err);
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), copyStaticFiles()],
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        sidebar: resolve(__dirname, 'src/index.jsx'),
        content: resolve(__dirname, 'src/content.js'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: '[name].js',
        assetFileNames: '[name].[ext]',
      },
    },
  },
});
