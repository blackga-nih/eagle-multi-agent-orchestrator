import { NextResponse } from 'next/server';
import { readFile, readdir, stat } from 'fs/promises';
import { join } from 'path';

const PROJECT_ROOT = join(process.cwd(), '..');
const EVAL_RESULTS_DIR = join(PROJECT_ROOT, 'data', 'eval', 'results');

/**
 * GET /api/trace-logs
 *
 * Query params:
 *   ?list=1          → returns metadata for all run-*.json files in data/eval/results/
 *   ?run=<filename>  → returns data from a specific file (e.g. run-2026-02-10T22-30-00Z.json)
 *   (none)           → returns latest.json (most recent run)
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const listMode = searchParams.get('list');
  const runFile = searchParams.get('run');

  try {
    if (listMode) {
      // List all run-*.json files with metadata
      const files = await readdir(EVAL_RESULTS_DIR);
      const traceFiles = files.filter(
        (f) => f.startsWith('run-') && f.endsWith('.json')
      );

      const runs = await Promise.all(
        traceFiles.map(async (filename) => {
          const filePath = join(EVAL_RESULTS_DIR, filename);
          const fileStat = await stat(filePath);
          try {
            const content = JSON.parse(
              await readFile(filePath, 'utf-8')
            );
            return {
              filename,
              timestamp: content.timestamp || fileStat.mtime.toISOString(),
              run_id: content.run_id || filename,
              total_tests: content.total_tests ?? Object.keys(content.results || {}).length,
              passed: content.passed ?? 0,
              failed: content.failed ?? 0,
              skipped: content.skipped ?? 0,
              size_bytes: fileStat.size,
            };
          } catch {
            return {
              filename,
              timestamp: fileStat.mtime.toISOString(),
              run_id: filename,
              total_tests: 0,
              passed: 0,
              failed: 0,
              skipped: 0,
              size_bytes: fileStat.size,
              parse_error: true,
            };
          }
        })
      );

      // Sort newest first
      runs.sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );

      return NextResponse.json({ runs });
    }

    // Load a specific run or latest.json
    const targetFile = runFile || 'latest.json';
    // Prevent directory traversal
    if (targetFile.includes('..') || targetFile.includes('/') || targetFile.includes('\\')) {
      return NextResponse.json({ error: 'Invalid filename' }, { status: 400 });
    }

    const filePath = join(EVAL_RESULTS_DIR, targetFile);
    const content = await readFile(filePath, 'utf-8');
    const data = JSON.parse(content);
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      {
        error:
          'No eval results found. Run python test_eagle_sdk_eval.py to generate results in data/eval/results/.',
      },
      { status: 404 }
    );
  }
}
