import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    globals: true,
    include: ['test/**/*.test.{js,ts}'],
    exclude: ['node_modules/', 'dist/', 'vps_instances/', 'data/', 'test_data/'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'dist/',
        'vps_instances/',
        'data/',
        'test_data/',
        '**/*.test.{js,ts}',
        'eslint.config.js',
        'vitest.config.ts',
        'test/setup.js'
      ]
    },
    setupFiles: ['test/setup.js'],
    testTimeout: 10000,
    hookTimeout: 10000
  }
});