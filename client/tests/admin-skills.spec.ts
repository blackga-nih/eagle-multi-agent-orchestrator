import { test, expect } from '@playwright/test';

test.describe('Admin Skills & Prompts Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/admin/skills/');
  });

  test('displays page header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Agent Skills & Prompts' })).toBeVisible();
    await expect(page.getByText('Configure AI agent capabilities and system prompts')).toBeVisible();
  });

  test('displays breadcrumb navigation', async ({ page }) => {
    await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
    await expect(page.getByText('Agent Skills').first()).toBeVisible();
  });

  test('has New Skill button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /New Skill/ })).toBeVisible();
  });

  test('has Refresh button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Refresh/ })).toBeVisible();
  });

  test('displays tab navigation with Skills and Agent Prompts', async ({ page }) => {
    await expect(page.getByText('Skills')).toBeVisible();
    await expect(page.getByText('Agent Prompts')).toBeVisible();
  });

  test('has search input', async ({ page }) => {
    await expect(page.getByPlaceholder('Search skills...')).toBeVisible();
  });

  test('search placeholder changes when switching to Prompts tab', async ({ page }) => {
    await page.getByText('Agent Prompts').click();
    await expect(page.getByPlaceholder('Search agent prompts...')).toBeVisible();
  });

  test('shows loading state or skill cards', async ({ page }) => {
    const loading = page.getByText('Loading data...');
    const bundledHeading = page.getByText('Bundled Skills');
    const customHeading = page.getByText('Custom Skills');
    const empty = page.getByText('No skills found.');

    await expect(loading.or(bundledHeading).or(customHeading).or(empty)).toBeVisible();
  });

  test('skill cards show name and version', async ({ page }) => {
    await page.waitForSelector('text=Loading data...', { state: 'hidden' }).catch(() => {});

    const cards = page.getByRole('heading', { level: 3 });
    const count = await cards.count();
    if (count > 0) {
      await expect(cards.first()).toBeVisible();
      // Version text should be present on cards
      const versionText = page.locator('text=/v\\d+/');
      await expect(versionText.first()).toBeVisible();
    }
  });

  test('bundled skills show Bundled badge', async ({ page }) => {
    await page.waitForSelector('text=Loading data...', { state: 'hidden' }).catch(() => {});

    const bundledBadge = page.getByText('Bundled', { exact: true });
    const count = await bundledBadge.count();
    if (count > 0) {
      await expect(bundledBadge.first()).toBeVisible();
    }
  });

  test('custom skills show status badges', async ({ page }) => {
    await page.waitForSelector('text=Loading data...', { state: 'hidden' }).catch(() => {});

    // Custom skills have status badges: Draft, In Review, Active, or Disabled
    const statusBadges = page.getByText('Draft')
      .or(page.getByText('In Review'))
      .or(page.getByText('Active'))
      .or(page.getByText('Disabled'));
    const count = await statusBadges.count();
    // Custom skills may or may not exist; just verify structure if present
    if (count > 0) {
      await expect(statusBadges.first()).toBeVisible();
    }
  });

  test('breadcrumb navigates back to admin dashboard', async ({ page }) => {
    await page.getByRole('link', { name: 'Admin' }).click();
    await expect(page).toHaveURL(/\/admin/);
  });
});
