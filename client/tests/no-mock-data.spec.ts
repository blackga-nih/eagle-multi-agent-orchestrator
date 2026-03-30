/**
 * Guard tests: ensure mock data never re-enters the codebase.
 *
 * These tests scan source files (not test files) for imports of the deleted
 * mock-data.ts module and for hardcoded mock IDs (wf-001, user-001, etc.).
 * They run without a browser — pure Node assertions.
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const CLIENT_DIR = path.resolve(__dirname, '..');
const LIB_DIR = path.join(CLIENT_DIR, 'lib');

/** Recursively collect .ts/.tsx source files, excluding node_modules and tests. */
function getSourceFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (['node_modules', '.next', 'tests', '.auth'].includes(entry.name)) continue;
      results.push(...getSourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith('.spec.ts')) {
      results.push(full);
    }
  }
  return results;
}

test.describe('No Mock Data Guard', () => {
  const sourceFiles = getSourceFiles(CLIENT_DIR);

  test('mock-data.ts file does not exist', () => {
    const mockDataPath = path.join(LIB_DIR, 'mock-data.ts');
    expect(fs.existsSync(mockDataPath)).toBe(false);
  });

  test('no source file imports from mock-data', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles) {
      const content = fs.readFileSync(file, 'utf-8');
      if (
        /from\s+['"]@\/lib\/mock-data['"]/.test(content) ||
        /from\s+['"]\.\.?\/.*mock-data['"]/.test(content)
      ) {
        offenders.push(path.relative(CLIENT_DIR, file));
      }
    }
    expect(offenders, `Files still importing mock-data: ${offenders.join(', ')}`).toHaveLength(0);
  });

  test('no source file references MOCK_ constants', () => {
    const pattern =
      /\bMOCK_(USERS|DOCUMENTS|DOCUMENT_TEMPLATES|AGENT_SKILLS|AUDIT_LOGS|USER_GROUPS|REQUIREMENTS|SUBMISSIONS|CONVERSATION_TURNS|SYSTEM_PROMPTS)\b/;
    const offenders: string[] = [];
    for (const file of sourceFiles) {
      const content = fs.readFileSync(file, 'utf-8');
      if (pattern.test(content)) {
        offenders.push(path.relative(CLIENT_DIR, file));
      }
    }
    expect(offenders, `Files referencing MOCK_ constants: ${offenders.join(', ')}`).toHaveLength(0);
  });

  test('no source file references CURRENT_USER from mock data', () => {
    // CURRENT_USER was the mock user object — should now use useAuth()
    const offenders: string[] = [];
    for (const file of sourceFiles) {
      const content = fs.readFileSync(file, 'utf-8');
      // Match CURRENT_USER as a standalone identifier, not in comments
      const lines = content.split('\n');
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('//') || trimmed.startsWith('*')) continue;
        if (/\bCURRENT_USER\b/.test(trimmed)) {
          offenders.push(path.relative(CLIENT_DIR, file));
          break;
        }
      }
    }
    expect(offenders, `Files referencing CURRENT_USER: ${offenders.join(', ')}`).toHaveLength(0);
  });

  test('no source file references CURRENT_WORKFLOW or PAST_WORKFLOWS', () => {
    const pattern = /\b(CURRENT_WORKFLOW|PAST_WORKFLOWS|CURRENT_CHECKLIST)\b/;
    const offenders: string[] = [];
    for (const file of sourceFiles) {
      const content = fs.readFileSync(file, 'utf-8');
      const lines = content.split('\n');
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('//') || trimmed.startsWith('*')) continue;
        if (pattern.test(trimmed)) {
          offenders.push(path.relative(CLIENT_DIR, file));
          break;
        }
      }
    }
    expect(
      offenders,
      `Files referencing mock workflow constants: ${offenders.join(', ')}`,
    ).toHaveLength(0);
  });

  test('no hardcoded mock IDs in source files', () => {
    // These are the fake IDs from the deleted mock data
    const mockIds = [
      'wf-001',
      'wf-002',
      'wf-003',
      'wf-004',
      'doc-001',
      'doc-002',
      'doc-003',
      'user-001',
      'user-002',
      'tpl-001',
      'cl-001',
    ];
    const offenders: { file: string; id: string }[] = [];

    for (const file of sourceFiles) {
      const content = fs.readFileSync(file, 'utf-8');
      for (const id of mockIds) {
        // Match as string literal, not in comments
        if (content.includes(`'${id}'`) || content.includes(`"${id}"`)) {
          offenders.push({ file: path.relative(CLIENT_DIR, file), id });
        }
      }
    }
    const summary = offenders.map((o) => `${o.file} (${o.id})`).join(', ');
    expect(offenders, `Hardcoded mock IDs found: ${summary}`).toHaveLength(0);
  });

  test('format-helpers.ts exists and exports required functions', () => {
    const helpersPath = path.join(LIB_DIR, 'format-helpers.ts');
    expect(fs.existsSync(helpersPath)).toBe(true);

    const content = fs.readFileSync(helpersPath, 'utf-8');
    const requiredExports = [
      'getWorkflowStatusColor',
      'getAcquisitionTypeLabel',
      'getDocumentStatusColor',
      'formatCurrency',
      'formatDate',
      'formatTime',
      'getRelativeTime',
      'getSkillTypeColor',
      'getUserRoleColor',
      'getUserRoleLabel',
      'mapAuthRoleToUserRole',
    ];
    for (const fn of requiredExports) {
      expect(content, `format-helpers.ts missing export: ${fn}`).toContain(`export function ${fn}`);
    }
  });

  test('document-store DEFAULT_CHECKLIST has at least 10 items', () => {
    const storePath = path.join(LIB_DIR, 'document-store.ts');
    const content = fs.readFileSync(storePath, 'utf-8');

    // Extract the DEFAULT_CHECKLIST array entries
    const match = content.match(/const DEFAULT_CHECKLIST[\s\S]*?\];/);
    expect(match).not.toBeNull();

    const checklistBlock = match![0];
    const itemCount = (checklistBlock.match(/document_type:/g) || []).length;
    expect(
      itemCount,
      `DEFAULT_CHECKLIST has ${itemCount} items, expected >= 10`,
    ).toBeGreaterThanOrEqual(10);
  });
});
