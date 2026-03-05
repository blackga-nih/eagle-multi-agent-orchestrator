#!/usr/bin/env python3
"""
Obsidian Vault Schema Generator
Analyzes an Obsidian vault and generates schemas in multiple formats.
"""
# /// script
# requires-python = ">=3.7"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///

import os
import re
import json
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Optional, Any
import hashlib


class ObsidianVaultParser:
    """Parse an Obsidian vault and extract structure, links, and metadata."""

    def __init__(self, vault_path: str, exclude_folders: Optional[List[str]] = None):
        self.vault_path = Path(vault_path)
        self.exclude_folders = exclude_folders or []
        self.notes: Dict[str, Dict] = {}
        self.links: List[Dict] = []
        self.folders: Dict[str, Dict] = defaultdict(lambda: {"note_count": 0, "subfolders": set()})
        self.tag_distribution: Dict[str, int] = defaultdict(int)

    def should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded from analysis."""
        # Exclude .obsidian folder and hidden files
        if any(part.startswith('.') for part in path.parts):
            return True

        # Exclude user-specified folders
        for exclude in self.exclude_folders:
            if exclude in str(path):
                return True

        return False

    def extract_frontmatter(self, content: str) -> tuple[Dict, str]:
        """Extract YAML frontmatter from markdown content."""
        frontmatter = {}
        body = content

        # Check for YAML frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2]
                except yaml.YAMLError:
                    pass  # Skip malformed frontmatter

        return frontmatter, body

    def extract_wikilinks(self, content: str) -> List[tuple[str, str]]:
        """Extract wikilinks from content. Returns list of (link_target, link_text) tuples."""
        # Match [[link]] and [[link|alias]]
        pattern = r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]'
        matches = re.findall(pattern, content)

        # Return (target, display_text)
        return [(match[0], match[1] if match[1] else match[0]) for match in matches]

    def extract_markdown_links(self, content: str) -> List[tuple[str, str]]:
        """Extract markdown links. Returns list of (link_target, link_text) tuples."""
        pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
        matches = re.findall(pattern, content)

        # Filter for .md files only
        return [(match[1], match[0]) for match in matches if match[1].endswith('.md')]

    def extract_tags(self, content: str, frontmatter: Dict) -> Set[str]:
        """Extract tags from content and frontmatter."""
        tags = set()

        # From frontmatter
        if 'tags' in frontmatter:
            fm_tags = frontmatter['tags']
            if isinstance(fm_tags, list):
                tags.update(fm_tags)
            elif isinstance(fm_tags, str):
                tags.add(fm_tags)

        # From content (#tag format)
        tag_pattern = r'#([\w/-]+)'
        content_tags = re.findall(tag_pattern, content)
        tags.update(content_tags)

        return tags

    def generate_note_id(self, file_path: Path) -> str:
        """Generate unique note ID from file path."""
        # Use hash of relative path for consistent IDs
        rel_path = file_path.relative_to(self.vault_path)
        return hashlib.md5(str(rel_path).encode()).hexdigest()[:12]

    def parse_note(self, file_path: Path) -> Optional[Dict]:
        """Parse a single markdown note."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"⚠️  Warning: Could not read {file_path}: {e}")
            return None

        frontmatter, body = self.extract_frontmatter(content)
        wikilinks = self.extract_wikilinks(body)
        md_links = self.extract_markdown_links(body)
        tags = self.extract_tags(body, frontmatter)

        # Update tag distribution
        for tag in tags:
            self.tag_distribution[tag] += 1

        # Get file metadata
        stat = file_path.stat()
        rel_path = file_path.relative_to(self.vault_path)

        note_id = self.generate_note_id(file_path)

        note_data = {
            "id": note_id,
            "title": file_path.stem,
            "path": str(rel_path),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size_bytes": stat.st_size,
            "word_count": len(body.split()),
            "tags": sorted(list(tags)),
            "frontmatter": frontmatter,
            "wikilinks": [{"target": link[0], "text": link[1]} for link in wikilinks],
            "markdown_links": [{"target": link[0], "text": link[1]} for link in md_links],
            "outbound_links": [],  # Will be populated later
            "inbound_links": [],   # Will be populated later
        }

        return note_data

    def scan_vault(self):
        """Scan entire vault and build note database."""
        print(f"🔍 Scanning vault: {self.vault_path}")

        # Find all markdown files
        md_files = []
        for md_file in self.vault_path.rglob("*.md"):
            if not self.should_exclude(md_file):
                md_files.append(md_file)

        print(f"📄 Found {len(md_files)} markdown files")

        # Parse each note
        for md_file in md_files:
            note_data = self.parse_note(md_file)
            if note_data:
                self.notes[note_data["id"]] = note_data

                # Update folder stats
                folder = md_file.parent.relative_to(self.vault_path)
                self.folders[str(folder)]["note_count"] += 1

        print(f"✅ Parsed {len(self.notes)} notes")

        # Build link graph
        self._build_link_graph()

        # Analyze folder hierarchy
        self._analyze_folders()

    def _build_link_graph(self):
        """Build bidirectional link graph between notes."""
        print("🔗 Building link graph...")

        # Create title to ID mapping for wikilink resolution
        title_to_id = {note["title"]: note_id for note_id, note in self.notes.items()}

        for note_id, note in self.notes.items():
            # Process wikilinks
            for wikilink in note["wikilinks"]:
                target_title = wikilink["target"]

                # Try to find target note
                target_id = title_to_id.get(target_title)

                if target_id:
                    # Add to outbound links
                    note["outbound_links"].append(target_id)

                    # Add to target's inbound links
                    self.notes[target_id]["inbound_links"].append(note_id)

                    # Create link record
                    self.links.append({
                        "source": note_id,
                        "target": target_id,
                        "link_text": wikilink["text"],
                        "link_type": "wikilink"
                    })

        print(f"✅ Found {len(self.links)} connections")

    def _analyze_folders(self):
        """Analyze folder hierarchy and relationships."""
        for folder_path in self.folders.keys():
            if folder_path != '.':
                parent = str(Path(folder_path).parent)
                if parent != '.':
                    self.folders[parent]["subfolders"].add(folder_path)

    def get_statistics(self) -> Dict:
        """Calculate vault statistics."""
        orphaned_notes = [
            note_id for note_id, note in self.notes.items()
            if len(note["inbound_links"]) == 0 and len(note["outbound_links"]) == 0
        ]

        # Find most connected note
        most_connected = max(
            self.notes.items(),
            key=lambda x: len(x[1]["inbound_links"]) + len(x[1]["outbound_links"]),
            default=(None, {})
        )

        total_links = sum(len(note["outbound_links"]) for note in self.notes.values())
        avg_links = total_links / len(self.notes) if self.notes else 0

        return {
            "total_notes": len(self.notes),
            "total_links": len(self.links),
            "total_folders": len(self.folders),
            "orphaned_notes": len(orphaned_notes),
            "orphaned_note_ids": orphaned_notes,
            "most_connected_note": most_connected[1].get("title", "N/A"),
            "most_connected_note_id": most_connected[0],
            "most_connected_link_count": len(most_connected[1].get("inbound_links", [])) + len(most_connected[1].get("outbound_links", [])),
            "average_links_per_note": round(avg_links, 2),
            "total_tags": len(self.tag_distribution),
            "tag_distribution": dict(sorted(self.tag_distribution.items(), key=lambda x: x[1], reverse=True)[:20])
        }

    def generate_json_schema(self, include_content: bool = False) -> Dict:
        """Generate JSON schema."""
        stats = self.get_statistics()

        schema = {
            "vault_info": {
                "name": self.vault_path.name,
                "path": str(self.vault_path),
                "scanned_at": datetime.now().isoformat(),
                **stats
            },
            "folders": [
                {
                    "path": folder_path,
                    "note_count": data["note_count"],
                    "subfolder_count": len(data["subfolders"]),
                    "subfolders": sorted(list(data["subfolders"]))
                }
                for folder_path, data in sorted(self.folders.items())
            ],
            "notes": list(self.notes.values()),
            "links": self.links,
            "statistics": stats
        }

        return schema

    def generate_yaml_schema(self) -> str:
        """Generate YAML schema."""
        schema = self.generate_json_schema()
        return yaml.dump(schema, default_flow_style=False, sort_keys=False)

    def generate_graphml(self) -> str:
        """Generate GraphML format for visualization tools."""
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_parts.append('<graphml xmlns="http://graphml.graphdrawing.org/xmlns">')
        xml_parts.append('  <key id="label" for="node" attr.name="label" attr.type="string"/>')
        xml_parts.append('  <key id="path" for="node" attr.name="path" attr.type="string"/>')
        xml_parts.append('  <key id="tags" for="node" attr.name="tags" attr.type="string"/>')
        xml_parts.append('  <key id="word_count" for="node" attr.name="word_count" attr.type="int"/>')
        xml_parts.append('  <graph id="G" edgedefault="directed">')

        # Add nodes
        for note_id, note in self.notes.items():
            xml_parts.append(f'    <node id="{note_id}">')
            xml_parts.append(f'      <data key="label">{self._escape_xml(note["title"])}</data>')
            xml_parts.append(f'      <data key="path">{self._escape_xml(note["path"])}</data>')
            xml_parts.append(f'      <data key="tags">{", ".join(note["tags"])}</data>')
            xml_parts.append(f'      <data key="word_count">{note["word_count"]}</data>')
            xml_parts.append('    </node>')

        # Add edges
        for i, link in enumerate(self.links):
            xml_parts.append(f'    <edge id="e{i}" source="{link["source"]}" target="{link["target"]}"/>')

        xml_parts.append('  </graph>')
        xml_parts.append('</graphml>')

        return '\n'.join(xml_parts)

    def _escape_xml(self, text: str) -> str:
        """Escape XML special characters."""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    def generate_markdown_report(self) -> str:
        """Generate human-readable markdown report."""
        stats = self.get_statistics()

        report = [
            f"# Vault Schema Report: {self.vault_path.name}",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Vault Path:** `{self.vault_path}`",
            "",
            "## Summary Statistics",
            "",
            f"- **Total Notes:** {stats['total_notes']}",
            f"- **Total Links:** {stats['total_links']}",
            f"- **Total Folders:** {stats['total_folders']}",
            f"- **Orphaned Notes:** {stats['orphaned_notes']}",
            f"- **Average Links per Note:** {stats['average_links_per_note']}",
            f"- **Total Unique Tags:** {stats['total_tags']}",
            "",
            "## Most Connected Note",
            "",
            f"**{stats['most_connected_note']}** - {stats['most_connected_link_count']} connections",
            "",
            "## Folder Structure",
            "",
            "| Folder | Notes | Subfolders |",
            "|--------|-------|------------|"
        ]

        for folder_path, data in sorted(self.folders.items(), key=lambda x: x[1]["note_count"], reverse=True):
            report.append(f"| `{folder_path}` | {data['note_count']} | {len(data['subfolders'])} |")

        report.extend([
            "",
            "## Top Tags",
            "",
            "| Tag | Count |",
            "|-----|-------|"
        ])

        for tag, count in list(stats['tag_distribution'].items())[:15]:
            report.append(f"| #{tag} | {count} |")

        if stats['orphaned_notes'] > 0:
            report.extend([
                "",
                f"## Orphaned Notes ({stats['orphaned_notes']})",
                "",
                "Notes with no incoming or outgoing links:",
                ""
            ])

            for note_id in stats['orphaned_note_ids'][:20]:
                note = self.notes[note_id]
                report.append(f"- `{note['path']}`")

            if len(stats['orphaned_note_ids']) > 20:
                report.append(f"\n_...and {len(stats['orphaned_note_ids']) - 20} more_")

        return '\n'.join(report)


def main():
    parser = argparse.ArgumentParser(description='Generate schema from Obsidian vault')
    parser.add_argument('--vault-path', required=True, help='Path to Obsidian vault')
    parser.add_argument('--schema-type', default='complete',
                       choices=['structure', 'links', 'metadata', 'complete'],
                       help='Type of schema to generate')
    parser.add_argument('--output-format', default='all',
                       choices=['json', 'yaml', 'graphml', 'markdown', 'all'],
                       help='Output format(s)')
    parser.add_argument('--output-dir', default='./vault-schema-output',
                       help='Output directory')
    parser.add_argument('--exclude-folders', default='',
                       help='Comma-separated folders to exclude')
    parser.add_argument('--include-content', action='store_true',
                       help='Include note content in schema')

    args = parser.parse_args()

    # Parse exclude folders
    exclude_folders = [f.strip() for f in args.exclude_folders.split(',') if f.strip()]

    # Create parser and scan vault
    vault_parser = ObsidianVaultParser(args.vault_path, exclude_folders)
    vault_parser.scan_vault()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate outputs
    formats = ['json', 'yaml', 'graphml', 'markdown'] if args.output_format == 'all' else [args.output_format]

    for fmt in formats:
        if fmt == 'json':
            schema = vault_parser.generate_json_schema(args.include_content)
            output_file = output_dir / 'vault_schema.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(schema, f, indent=2, ensure_ascii=False)
            print(f"📄 Generated: {output_file}")

        elif fmt == 'yaml':
            yaml_content = vault_parser.generate_yaml_schema()
            output_file = output_dir / 'vault_schema.yaml'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(yaml_content)
            print(f"📄 Generated: {output_file}")

        elif fmt == 'graphml':
            graphml_content = vault_parser.generate_graphml()
            output_file = output_dir / 'vault_graph.graphml'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(graphml_content)
            print(f"📄 Generated: {output_file}")

        elif fmt == 'markdown':
            report = vault_parser.generate_markdown_report()
            output_file = output_dir / 'VAULT_SCHEMA_REPORT.md'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"📄 Generated: {output_file}")

    # Print summary
    stats = vault_parser.get_statistics()
    print("\n" + "="*50)
    print("✅ Schema generation complete!")
    print("="*50)
    print(f"\n📊 Summary:")
    print(f"  - Total notes: {stats['total_notes']}")
    print(f"  - Total links: {stats['total_links']}")
    print(f"  - Orphaned notes: {stats['orphaned_notes']}")
    print(f"  - Folders: {stats['total_folders']}")
    print(f"  - Most connected: \"{stats['most_connected_note']}\" ({stats['most_connected_link_count']} links)")
    print(f"\n📁 Output directory: {output_dir.absolute()}")


if __name__ == '__main__':
    main()
