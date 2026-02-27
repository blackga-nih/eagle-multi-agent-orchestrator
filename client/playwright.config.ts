import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for Eagle Intake App integration tests.
 *
 * Runs against the deployed ECS environment by default.
 * Set BASE_URL environment variable to test other environments.
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : parseInt(process.env.WORKERS || '4'),
  reporter: 'html',

  // Run global-setup.ts once before all tests to log in and save auth state
  globalSetup: './tests/global-setup.ts',

  use: {
    // Base URL for the deployed application
    baseURL: process.env.BASE_URL || 'http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com',

    // Reuse Cognito session saved by global-setup — all tests start authenticated
    storageState: 'tests/.auth/user.json',

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',
  },

  projects: [
    // Auth setup runs once — saves session to tests/.auth/user.json
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
      use: { storageState: undefined }, // setup project must NOT use saved state
    },

    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: 'tests/.auth/user.json' },
      dependencies: ['setup'],
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'], storageState: 'tests/.auth/user.json' },
      dependencies: ['setup'],
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'], storageState: 'tests/.auth/user.json' },
      dependencies: ['setup'],
    },
    // Mobile viewports
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'], storageState: 'tests/.auth/user.json' },
      dependencies: ['setup'],
    },
  ],
});
