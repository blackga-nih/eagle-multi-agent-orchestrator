# Asset Ownership

This document records the current canonical ownership for templates and diagrams after the 2026-03 refactor.

## Templates

Runtime document generation source:
- `server/app/template_registry.py` backed by S3 templates

Schema/completeness guidance source:
- `eagle-plugin/data/templates/`

Notes:
- The markdown files in `eagle-plugin/data/templates/` are still consumed by `server/app/template_schema.py` for section guidance and completeness validation.
- They are not the primary runtime source for generated DOCX/XLSX/PDF artifacts.

## Diagrams

Canonical docs-owned authoring paths:
- `docs/architecture/diagrams/excalidraw/`
- `docs/architecture/diagrams/mermaid/`

Generated/exported docs artifacts:
- `docs/architecture/diagrams/exports/`

Notes:
- Duplicate docs-owned copies under `docs/excalidraw-diagrams/` and `docs/architecture/diagrams/mermaid-diagrams/mermaid/` were removed during refactor cleanup.
- `eagle-plugin/diagrams/` is currently treated as a separate plugin-owned artifact tree until a generation workflow is defined.
