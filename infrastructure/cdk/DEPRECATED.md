# DEPRECATED

This Python CDK project (`MultiTenantBedrockStack`) is **not deployed** and has been superseded by the TypeScript CDK project at `infrastructure/cdk-eagle/`.

## Replacement

| Old (Python) | New (TypeScript) |
|--------------|------------------|
| `infrastructure/cdk/app.py` | `infrastructure/cdk-eagle/bin/eagle.ts` |
| `MultiTenantBedrockStack` | `EagleCoreStack` + `EagleComputeStack` + `EagleCiCdStack` |
| `tenant-sessions` table | Unified `eagle` table |
| `tenant-usage` table | Unified `eagle` table |
| Static IAM keys | GitHub Actions OIDC |

## Migration

See `.claude/specs/aws-comprehensive-cdk.md` for the full migration plan.

This directory is kept as a reference only. Do not deploy from here.
