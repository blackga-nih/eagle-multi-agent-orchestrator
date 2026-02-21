# Lambda Windows→Linux Cross-Platform Bundler

**Date**: 2026-02-20
**Domain**: aws / lambda
**Triggered by**: pydantic_core native extension failure (Windows binary deployed to Linux Lambda)

---

## Problem

CDK's `local.tryBundle()` in `storage-stack.ts` runs `pip install` on the host machine.
On Windows, pip installs Windows binary wheels (`.pyd`, `.dll`). Lambda runs Linux x86_64.
Native C extensions fail at import time: `No module named 'pydantic_core._pydantic_core'`.

Current workaround: replaced `pydantic` with stdlib `dataclasses` (no native extensions).
This is a one-off fix — the root cause (Windows pip installs wrong platform) remains.

---

## Root Cause

```
CDK tryBundle() → runs on Windows → pip installs Windows wheels
Lambda runtime → Linux x86_64 → import fails for native extension packages
```

pip does NOT cross-compile by default. Without `--platform`, it always installs
the wheel for the current OS.

---

## Solution

**Create `infrastructure/cdk-eagle/scripts/bundle-lambda.py`** — a cross-platform
Lambda dependency bundler that:

1. Detects host OS (`platform.system()`)
2. **On Windows**: uses `pip install --platform manylinux2014_x86_64 --only-binary :all:`
   to download Linux-compatible binary wheels (manylinux = Lambda-compatible)
3. **On Linux**: standard pip install (native platform matches Lambda)
4. **Fallback**: if `--platform` install fails (package not available as manylinux wheel),
   warns and falls back to host-platform install
5. Copies all `.py` source files from the Lambda source dir to the output dir

**Update `storage-stack.ts`** `local.tryBundle()` to invoke the script instead of
calling pip directly.

---

## Files

| File | Action |
|------|--------|
| `infrastructure/cdk-eagle/scripts/bundle-lambda.py` | CREATE — cross-platform bundler |
| `infrastructure/cdk-eagle/lib/storage-stack.ts` | UPDATE — local bundler calls script |
| `.claude/commands/experts/aws/expertise.md` | UPDATE — add Lambda bundling patterns |

---

## Key pip flags

```bash
# Install Linux manylinux wheels on any host OS:
pip install \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 312 \
  --only-binary :all: \
  -t /output \
  -r requirements.txt
```

`manylinux2014_x86_64` is the Lambda-compatible wheel tag. Packages on PyPI that
provide `manylinux2014_x86_64` or `manylinux1_x86_64` wheels will install correctly.
Pure-Python packages (no native extensions) always work regardless of platform.

---

## Validation

1. `npm run build && npx cdk synth --quiet` — CDK compiles
2. `npx cdk deploy EagleStorageStack` — Lambda redeployed
3. Invoke Lambda with test S3 event — no import errors
4. Check Lambda logs — successful execution (or only downstream errors, not import errors)

---

## Rollback

- `git checkout infrastructure/cdk-eagle/lib/storage-stack.ts` — reverts to direct pip
- `git checkout infrastructure/cdk-eagle/lambda/metadata-extraction/requirements.txt`
- The pydantic→dataclasses change in models.py is safe to keep (reduces dependencies)
