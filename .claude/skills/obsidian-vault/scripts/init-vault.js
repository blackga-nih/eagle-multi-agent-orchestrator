#!/usr/bin/env node

/**
 * Obsidian Vault Initialization Script
 *
 * This script creates the folder structure and initial files
 * in your Obsidian vault for Claude Code integration.
 *
 * Usage: node init-vault.js
 */

const fs = require('fs');
const path = require('path');

// Load vault settings
function loadVaultSettings() {
  const configPath = path.join(__dirname, '../config/vault-settings.json');
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  return config;
}

// Create directory if it doesn't exist
function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
    console.log(`✓ Created: ${dirPath}`);
  } else {
    console.log(`• Exists: ${dirPath}`);
  }
}

// Copy template file
function copyTemplate(templateName, destPath) {
  const templatePath = path.join(__dirname, '../templates', templateName);

  if (!fs.existsSync(destPath)) {
    const content = fs.readFileSync(templatePath, 'utf8');
    fs.writeFileSync(destPath, content);
    console.log(`✓ Created template: ${destPath}`);
  } else {
    console.log(`• Template exists: ${destPath}`);
  }
}

// Main initialization function
function initializeVault() {
  console.log('='.repeat(60));
  console.log('Obsidian Vault Initialization');
  console.log('='.repeat(60));
  console.log();

  // Load configuration
  const config = loadVaultSettings();
  const vaultPath = config.vaultPath;
  const projectFolder = config.projectFolder;

  // Validate vault path
  if (!fs.existsSync(vaultPath)) {
    console.error(`❌ Error: Vault path does not exist: ${vaultPath}`);
    console.error('   Please update vaultPath in config/vault-settings.json');
    process.exit(1);
  }

  console.log(`Vault Path: ${vaultPath}`);
  console.log(`Project Folder: ${projectFolder}`);
  console.log();

  // Create base project folder
  const projectPath = path.join(vaultPath, projectFolder);
  ensureDir(projectPath);

  // Create folder structure
  console.log('\nCreating folder structure...');
  const folders = [
    config.folders.dailyNotes,
    config.folders.decisions,
    path.join(config.folders.decisions, 'Architecture'),
    config.folders.learnings,
    config.folders.tasks,
    config.folders.meetings,
    config.folders.templates
  ];

  folders.forEach(folder => {
    ensureDir(path.join(projectPath, folder));
  });

  // Copy templates to vault
  console.log('\nCopying templates...');
  const templatesFolder = path.join(projectPath, config.folders.templates);

  copyTemplate('daily-note.md', path.join(templatesFolder, 'daily-note.md'));
  copyTemplate('adr.md', path.join(templatesFolder, 'adr.md'));
  // Add more templates as needed

  // Create project index
  console.log('\nCreating project index...');
  const indexPath = path.join(projectPath, 'INDEX.md');
  if (!fs.existsSync(indexPath)) {
    const indexContent = `---
title: ${path.basename(projectFolder)} Index
tags: [index, moc]
created: ${new Date().toISOString()}
---

# ${path.basename(projectFolder)} Index

## 📁 Folder Structure

- [[${config.folders.dailyNotes}]] - Daily notes and journal
- [[${config.folders.decisions}]] - Architecture Decision Records
- [[${config.folders.learnings}]] - Knowledge and learnings
- [[${config.folders.tasks}]] - Task tracking
- [[${config.folders.meetings}]] - Meeting notes

## 🔗 Quick Links

### Recent Notes
<!-- Recent notes will appear here -->

### Key Decisions
<!-- Link to important ADRs -->

### Active Tasks
<!-- Current tasks -->

---

*This index is maintained by Claude Code*
`;

    fs.writeFileSync(indexPath, indexContent);
    console.log(`✓ Created: ${indexPath}`);
  }

  // Create .claudeignore if needed
  console.log('\nChecking .claudeignore...');
  const claudeignorePath = path.join(projectPath, '.claudeignore');
  if (!fs.existsSync(claudeignorePath)) {
    const ignoreContent = `# Claude Code ignore patterns
# Add folders/files that Claude should not access

Private/
Archive/
*.private.md
`;
    fs.writeFileSync(claudeignorePath, ignoreContent);
    console.log(`✓ Created: ${claudeignorePath}`);
  }

  // Success summary
  console.log();
  console.log('='.repeat(60));
  console.log('✓ Vault initialization complete!');
  console.log('='.repeat(60));
  console.log();
  console.log('Next steps:');
  console.log('1. Open Obsidian and navigate to:', projectPath);
  console.log('2. Verify folder structure exists');
  console.log('3. Test integration with: /daily-note');
  console.log('4. Try creating a note: /note-create "Test"');
  console.log();
  console.log('For help, see: .claude/OBSIDIAN_QUICK_START.md');
  console.log();
}

// Run initialization
try {
  initializeVault();
} catch (error) {
  console.error('❌ Error during initialization:', error.message);
  console.error(error.stack);
  process.exit(1);
}
