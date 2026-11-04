import { defineConfig, loadEnv } from 'vite';
import { tanstackStart } from '@tanstack/react-start/plugin/vite';
import react from '@vitejs/plugin-react';
import { nitro } from 'nitro/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig(({ mode }) => {
  // Server-only settings stay in process.env; only VITE_* variables may enter browser code.
  const env = loadEnv(mode, process.cwd(), '');
  for (const [key, value] of Object.entries(env)) process.env[key] ??= value;
  return {
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: { host: '127.0.0.1', port: 3003, strictPort: true },
    plugins: [tanstackStart(), nitro({ preset: 'node-server' }), react()],
  };
});
