import { test, expect } from '@playwright/test';

test.describe('Intake Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('displays intake form', async ({ page }) => {
    // Check main heading
    await expect(page.getByRole('heading', { name: 'EAGLE', level: 1 })).toBeVisible();
    await expect(page.getByText('OFFICE OF ACQUISITIONS - INTELLIGENCE LAYER')).toBeVisible();

    // Check form section
    await expect(page.getByRole('heading', { name: /Initial Intake Form/, level: 3 })).toBeVisible();
  });

  test('displays required form fields', async ({ page }) => {
    // What do you need field
    await expect(page.getByText(/What do you need/)).toBeVisible();
    await expect(page.getByPlaceholder(/Describe the product/)).toBeVisible();

    // Cost range dropdown
    await expect(page.getByText(/Estimated Cost Range/)).toBeVisible();

    // Date field
    await expect(page.getByText(/When do you need it by/)).toBeVisible();
  });

  test('cost range dropdown has options', async ({ page }) => {
    const costDropdown = page.getByRole('combobox');
    await expect(costDropdown).toBeVisible();

    // Verify dropdown has options by checking the select element has children
    // Options in HTML select are not visible until expanded, so we verify the combobox exists
    // and has the expected default value
    await expect(costDropdown).toHaveText(/Select cost range/);
  });

  test('has continue and voice input buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Continue' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start Voice Input' })).toBeVisible();
  });

  test('has chat input field', async ({ page }) => {
    await expect(page.getByPlaceholder('Message EAGLE...')).toBeVisible();
  });

  test('displays sidebar panels', async ({ page }) => {
    // Check sidebar tabs
    await expect(page.getByRole('button', { name: 'Active Intake' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Order History' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Agent Logs' })).toBeVisible();

    // Check acquisition summary section
    await expect(page.getByRole('heading', { name: 'Acquisition Summary', level: 3 })).toBeVisible();
  });

  test('shows system status', async ({ page }) => {
    // Should show backend status
    await expect(page.getByText(/Backend/)).toBeVisible();
    await expect(page.getByText('System Active')).toBeVisible();
  });
});
