# Codebase Restructuring Plan

This document outlines the proposed restructuring plan to achieve a cleaner, simpler codebase structure inspired by AWS QuickStart patterns.

## Current State Analysis

### Issues Identified

1. **Root Level Clutter**
   - Multiple Docker files at root
   - Scripts directory at root level
   - Mixed concerns (plugin, notes, data at root)
   - Configuration files scattered

2. **Inconsistent Organization**
   - `eagle-plugin/` is a separate project but mixed with main app
   - `notes/` directory at root level
   - `data/` directory at root level
   - `.claude/` configuration mixed with source code

3. **Naming Inconsistencies**
   - `client/` vs `server/` (could be `frontend/` and `backend/`)
   - Mixed naming conventions

4. **Documentation Scattered**
   - README at root
   - Documentation in `notes/`
   - Plugin docs in `eagle-plugin/`
   - No centralized docs structure

## Proposed Structure

### Target Structure (AWS QuickStart Style)

```
.
├── README.md                    # Main project overview
├── LICENSE                      # License file
├── .gitignore                   # Git ignore rules
├── docker-compose.yml           # Docker compose (renamed, moved configs)
│
├── source/                      # All source code
│   ├── frontend/                # Renamed from client/
│   │   ├── package.json
│   │   ├── next.config.mjs
│   │   └── [Next.js app structure]
│   │
│   └── backend/                 # Renamed from server/
│       ├── requirements.txt
│       ├── app/
│       └── [FastAPI structure]
│
├── infrastructure/              # Renamed from infra/
│   ├── terraform/
│   ├── cdk/
│   └── eval/
│
├── deployment/                  # New: Deployment scripts and configs
│   ├── scripts/                 # Moved from root scripts/
│   ├── docker/                  # Docker files
│   │   ├── Dockerfile.backend
│   │   └── Dockerfile.frontend
│   └── docker-compose.yml       # Moved from root
│
├── docs/                        # Centralized documentation
│   ├── architecture/            # Architecture docs
│   ├── deployment/              # Deployment guides
│   ├── development/             # Development setup
│   ├── api/                     # API documentation
│   └── codebase-structure.md    # Structure documentation
│
├── tests/                       # Top-level test organization
│   ├── e2e/                     # End-to-end tests
│   ├── integration/             # Integration tests
│   └── unit/                    # Unit tests
│
├── tools/                       # Development tools and utilities
│   ├── scripts/                 # Utility scripts
│   └── configs/                 # Tool configurations
│
└── .github/                     # GitHub workflows (if applicable)
    └── workflows/
```

### Alternative: Keep Current Names (Minimal Change)

If you prefer to keep `client/` and `server/` naming:

```
.
├── README.md
├── LICENSE
├── .gitignore
│
├── client/                      # Keep as-is
├── server/                      # Keep as-is
│
├── infrastructure/              # Renamed from infra/
│
├── deployment/                  # New: Deployment artifacts
│   ├── docker/
│   └── scripts/                 # Moved from root
│
├── docs/                        # Centralized docs
│
├── tests/                       # Top-level tests (optional)
│
└── tools/                       # Development tools
```

## Detailed Restructuring Steps

### Phase 1: Create New Structure (Non-Breaking)

1. **Create New Directories**
   ```bash
   mkdir -p docs/architecture docs/deployment docs/development docs/api
   mkdir -p deployment/docker deployment/scripts
   mkdir -p tools/scripts tools/configs
   ```

2. **Move Documentation**
   - Move `notes/instructions/*.md` → `docs/development/`
   - Create `docs/architecture/` for architecture diagrams and docs
   - Create `docs/deployment/` for deployment guides
   - Keep `README.md` at root (main entry point)

3. **Move Deployment Artifacts**
   - Move `Dockerfile.backend` → `deployment/docker/Dockerfile.backend`
   - Move `docker-compose.dev.yml` → `deployment/docker-compose.dev.yml`
   - Move `scripts/*.py` → `deployment/scripts/`
   - Move `scripts/*.sh` → `deployment/scripts/`

4. **Rename Infrastructure Directory**
   - Rename `infra/` → `infrastructure/`
   - Update all references in documentation and scripts

### Phase 2: Optional Renaming (Breaking Changes)

**Option A: Rename client/server to frontend/backend**
- Rename `client/` → `source/frontend/`
- Rename `server/` → `source/backend/`
- Update all import paths, documentation, and scripts
- Update Docker files and deployment scripts

**Option B: Keep client/server names**
- No changes needed
- Document the naming convention

### Phase 3: Organize Supporting Directories

1. **Eagle Plugin**
   - **Option 1**: Keep at root (if it's a core part of the project)
   - **Option 2**: Move to `tools/eagle-plugin/` (if it's a development tool)
   - **Option 3**: Move to separate repository (if it's a separate project)

2. **Data Directory**
   - **Option 1**: Keep `data/` at root (if it's runtime data)
   - **Option 2**: Move to `tools/data/` (if it's development/test data)
   - **Option 3**: Move to `.data/` (if it should be gitignored)

3. **Claude Configuration**
   - Keep `.claude/` at root (standard location for IDE configs)
   - Document its purpose in `docs/development/`

### Phase 4: Clean Up Root Level

1. **Remove/Relocate Root Files**
   - Move `snap_debug.txt` → `tools/` or delete if temporary
   - Ensure only essential files at root:
     - `README.md`
     - `LICENSE`
     - `.gitignore`
     - `.gitattributes` (if exists)
     - `docker-compose.yml` (if needed at root for convenience)

2. **Update Documentation**
   - Update all paths in documentation
   - Update README.md with new structure
   - Create migration guide for developers

## Migration Checklist

### Pre-Migration
- [ ] Review and approve restructuring plan
- [ ] Create backup branch
- [ ] Document current structure (baseline)
- [ ] Identify all scripts/configs that reference old paths

### Phase 1: Non-Breaking Changes
- [ ] Create new directory structure
- [ ] Move documentation files
- [ ] Move deployment artifacts
- [ ] Rename `infra/` to `infrastructure/`
- [ ] Update documentation references
- [ ] Test that nothing breaks

### Phase 2: Optional Renaming (if chosen)
- [ ] Rename `client/` → `source/frontend/` (or keep)
- [ ] Rename `server/` → `source/backend/` (or keep)
- [ ] Update all import paths
- [ ] Update Docker files
- [ ] Update CI/CD pipelines
- [ ] Update documentation

### Phase 3: Supporting Directories
- [ ] Decide on `eagle-plugin/` location
- [ ] Decide on `data/` location
- [ ] Move or document decisions
- [ ] Update `.gitignore` if needed

### Phase 4: Cleanup
- [ ] Remove temporary files
- [ ] Clean root directory
- [ ] Update all documentation
- [ ] Update README.md
- [ ] Create migration guide

### Post-Migration
- [ ] Verify all tests pass
- [ ] Verify deployment scripts work
- [ ] Update CI/CD if needed
- [ ] Communicate changes to team
- [ ] Update onboarding documentation

## Recommended Approach

### Minimal Disruption (Recommended)

1. **Keep current naming** (`client/`, `server/`)
2. **Rename only** `infra/` → `infrastructure/`
3. **Create** `deployment/` directory and move deployment artifacts
4. **Create** `docs/` directory and organize documentation
5. **Keep** `eagle-plugin/` at root (if it's core to the project)
6. **Move** `data/` to `.data/` or `tools/data/` if it's not runtime data

### Benefits
- Minimal breaking changes
- Clearer organization
- Easier to navigate
- Follows AWS QuickStart patterns
- Maintains backward compatibility where possible

## File Path Updates Required

### Documentation Updates
- `README.md` - Update all paths
- `docs/codebase-structure.md` - Reflect new structure
- All markdown files in `notes/` → `docs/`

### Script Updates
- `deployment/scripts/*.py` - Update import paths if needed
- `deployment/scripts/*.sh` - Update directory references
- CI/CD pipeline files - Update paths

### Configuration Updates
- `docker-compose.dev.yml` - Update paths to services
- Dockerfiles - Update COPY paths if needed
- Terraform/CDK - Update any local file references

## Rollback Plan

If issues arise:
1. Revert to backup branch
2. Document issues encountered
3. Revise plan based on learnings
4. Re-attempt with adjustments

## Timeline Estimate

- **Phase 1** (Non-breaking): 2-4 hours
- **Phase 2** (Optional renaming): 4-8 hours (if chosen)
- **Phase 3** (Supporting dirs): 1-2 hours
- **Phase 4** (Cleanup): 1-2 hours
- **Testing & Verification**: 2-4 hours

**Total**: 10-20 hours depending on scope

## Questions to Resolve

1. **Naming**: Keep `client/server` or rename to `frontend/backend`?
2. **Eagle Plugin**: Is it core to the project or a separate tool?
3. **Data Directory**: Runtime data or development/test data?
4. **Breaking Changes**: Are we okay with breaking changes, or prefer minimal disruption?
5. **CI/CD**: Do we have CI/CD pipelines that need updating?

## Next Steps

1. Review and approve this plan
2. Answer questions above
3. Create backup branch
4. Execute Phase 1 (non-breaking changes)
5. Test thoroughly
6. Proceed with additional phases if approved
