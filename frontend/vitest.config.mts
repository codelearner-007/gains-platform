import path from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'node',
    include: ['src/tests/*.ts'],
    env: {
      NEXT_PUBLIC_SUPABASE_ANON_KEY: 'vitest-anon-key',
      PRIVATE_SUPABASE_SERVICE_KEY: 'vitest-service-role-key',
    },
  },
});
