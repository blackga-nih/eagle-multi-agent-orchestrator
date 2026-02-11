import { NextResponse } from 'next/server';
import { readFile, readdir, stat } from 'fs/promises';
import { join } from 'path';

/** Auto-discover agents and skills from eagle-plugin directory structure. */
async function discoverEntries(
  baseDir: string,
  filename: string,
  typeLabel: string
): Promise<Record<string, { title: string; path: string }>> {
  const entries: Record<string, { title: string; path: string }> = {};
  try {
    const dirs = await readdir(baseDir);
    for (const dir of dirs) {
      const dirPath = join(baseDir, dir);
      const dirStat = await stat(dirPath);
      if (!dirStat.isDirectory()) continue;
      const filePath = join(dirPath, filename);
      try {
        await stat(filePath);
        // Extract title from first markdown heading or use directory name
        const content = await readFile(filePath, 'utf-8');
        const headingMatch = content.match(/^#\s+(.+)$/m);
        const nameMatch = content.match(/^name:\s*(.+)$/m);
        const title = headingMatch?.[1] || nameMatch?.[1] || `${dir} ${typeLabel}`;
        const relativePath = filePath.split('eagle-plugin')[1];
        entries[dir] = {
          title: title.trim(),
          path: `eagle-plugin${relativePath}`,
        };
      } catch {
        // No matching file in this directory — skip
      }
    }
  } catch {
    // Base directory doesn't exist — return empty
  }
  return entries;
}

export async function GET() {
  const projectRoot = join(process.cwd(), '..');
  const pluginDir = join(projectRoot, 'eagle-plugin');

  // Auto-discover agents and skills
  const agents = await discoverEntries(join(pluginDir, 'agents'), 'agent.md', 'Agent');
  const skills = await discoverEntries(join(pluginDir, 'skills'), 'SKILL.md', 'Skill');

  const allEntries = { ...agents, ...skills };

  const results: Record<string, { title: string; file: string; content: string }> = {};

  for (const [key, meta] of Object.entries(allEntries)) {
    try {
      const filePath = join(projectRoot, meta.path);
      const content = await readFile(filePath, 'utf-8');
      results[key] = {
        title: meta.title,
        file: meta.path,
        content,
      };
    } catch {
      results[key] = {
        title: meta.title,
        file: meta.path,
        content: `[Error: Could not read ${meta.path}]`,
      };
    }
  }

  return NextResponse.json(results);
}
