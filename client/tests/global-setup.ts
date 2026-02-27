import { chromium, FullConfig } from '@playwright/test';

/**
 * Global setup: log in once and save browser storage state to .auth/user.json.
 * All tests load this state via `storageState` in playwright.config.ts so they
 * start already authenticated.
 *
 * Handles two modes automatically:
 *   - Dev mode (local docker stack): frontend has no Cognito config, so the app
 *     uses a mock user and immediately redirects away from /login. No credentials
 *     needed — just save the (empty) storage state.
 *   - Prod mode (deployed stack): Cognito login form appears. Fill with
 *     TEST_EMAIL / TEST_PASSWORD (defaults to testuser@example.com / EagleTest2024!).
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use?.baseURL ?? 'http://localhost:3000';
  const email = process.env.TEST_EMAIL ?? 'testuser@example.com';
  const password = process.env.TEST_PASSWORD ?? 'EagleTest2024!';

  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Navigate to /login and see what happens
  await page.goto(`${baseURL}/login`);

  // Race: either the login form appears (prod) or the page redirects away (dev mode)
  const onLoginPage = await Promise.race([
    page.waitForSelector('#login-email', { timeout: 8000 }).then(() => true),
    page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 8000 }).then(() => false),
  ]).catch(() => false); // if both timeout, assume dev mode

  if (onLoginPage) {
    // Prod mode: fill credentials and submit
    await page.fill('#login-email', email);
    await page.fill('#login-password', password);
    await page.click('button[type="submit"]');

    // Wait for redirect away from /login
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 30000 });
  }
  // else: dev mode auto-redirected — already authenticated, nothing to do

  // Save storage state (Cognito localStorage tokens in prod; empty in dev mode)
  await page.context().storageState({ path: 'tests/.auth/user.json' });

  await browser.close();
}
