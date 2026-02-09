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
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',

  use: {
    // Base URL for the deployed application
    baseURL: process.env.BASE_URL || 'http://nci-ea-front-o7mgyip4dvih-1328022277.us-east-1.elb.amazonaws.com',

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    // Mobile viewports
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
  ],
});
