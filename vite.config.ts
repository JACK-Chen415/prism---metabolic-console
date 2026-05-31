import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(() => {
    const chunkNameFromViewPath = (id: string): string | undefined => {
      const normalized = id.split(path.sep).join('/');
      const marker = '/components/views/';
      if (!normalized.includes(marker)) return undefined;
      const fileName = normalized.split(marker)[1]?.split('.')[0];
      return fileName ? `view-${fileName.replace(/([a-z])([A-Z])/g, '$1-$2').toLowerCase()}` : undefined;
    };

    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
      },
      plugins: [react()],
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      },
      build: {
        rollupOptions: {
          output: {
            manualChunks(id) {
              if (id.includes('node_modules/react')) return 'react';
              if (id.includes('node_modules/marked') || id.includes('node_modules/dompurify')) return 'markdown';
              if (id.includes('node_modules/dexie')) return 'storage';
              return chunkNameFromViewPath(id);
            },
          },
        },
      }
    };
});
