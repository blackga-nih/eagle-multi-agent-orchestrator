import { defineConfig, devices } from '@playwright/test';
import path from 'path';

/**
 * Eval-specific Playwright config — screenshots on every test,
 * Chromium only, targets localhost:3000.
 */
const authState = path.join(__dirname, '.auth', 'user.json');

export default defineConfig({
  testDir: '.',
  fullyParallel: true,
  retries: 0,
  workers: 4,
  reporter: 'list',

  globalSetup: './global-setup.ts',

  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    storageState: authState,
    trace: 'off',
    screenshot: 'on',
    video: 'off',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: authState },
    },
  ],
});
