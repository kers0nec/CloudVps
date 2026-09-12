import { beforeAll, afterAll } from 'vitest';
import { rmSync, existsSync } from 'fs';
import { join } from 'path';

beforeAll(() => {
  // Setup test environment
  process.env.NODE_ENV = 'test';
  process.env.PORT = '3001';
});

afterAll(() => {
  // Cleanup test data directories
  const testDirs = [
    join(process.cwd(), 'test_data'),
    join(process.cwd(), 'vps_instances', 'test-vps'),
    join(process.cwd(), 'vps_instances', 'test-vps2')
  ];

  for (const dir of testDirs) {
    if (existsSync(dir)) {
      rmSync(dir, { recursive: true, force: true });
    }
  }
});