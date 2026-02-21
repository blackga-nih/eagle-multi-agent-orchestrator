#!/usr/bin/env python
"""
bundle-lambda.py — Cross-platform Lambda dependency bundler.

Ensures Python Lambda packages are compiled for Linux x86_64 regardless
of whether you're developing on Windows, macOS, or Linux.

ROOT CAUSE THIS SOLVES
----------------------
CDK's local.tryBundle() runs pip on the host machine. On Windows, pip installs
Windows binary wheels (.pyd, .dll). Lambda runs Linux x86_64. Native C extensions
(numpy, pydantic_core, cryptography, etc.) fail at import time with:
  "Unable to import module 'handler': No module named 'xxx._xxx'"

STRATEGY
--------
1. On Windows → pip --platform manylinux2014_x86_64 --only-binary :all:
   Downloads Linux-compatible manylinux wheels from PyPI.
   manylinux2014_x86_64 is the Lambda-compatible ABI tag.

2. If --platform install fails (package has no manylinux wheel) → warn + fallback
   Pure-Python packages always work; this only affects packages with native extensions.

3. On Linux/macOS → standard pip install
   Native platform is already Lambda-compatible (Linux) or close enough (macOS arm64 CI
   should use --platform too, but that's a rarer case).

USAGE (called by CDK local.tryBundle)
--------------------------------------
  python bundle-lambda.py <requirements.txt> <output_dir> <source_dir>

  requirements.txt : path to requirements file
  output_dir       : CDK asset output directory (absolute path)
  source_dir       : Lambda source directory containing .py files

EXIT CODES
----------
  0 = success
  1 = fatal error (CDK will fall back to Docker bundling)
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

# Lambda Python 3.12 target ABI tags
LAMBDA_PLATFORM = "manylinux2014_x86_64"
LAMBDA_IMPLEMENTATION = "cp"
LAMBDA_PYTHON_VERSION = "312"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, printing the command for transparency."""
    print(f"[bundle-lambda] $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, **kwargs)


def install_linux_platform(requirements_file: str, output_dir: str) -> bool:
    """
    Install Linux manylinux wheels using pip --platform.
    Works on any host OS — pip downloads the Linux-targeted wheels from PyPI.
    Returns True on success, False if any package lacks a manylinux wheel.
    """
    result = _run(
        [
            sys.executable, "-m", "pip", "install",
            "-r", requirements_file,
            "-t", output_dir,
            "--platform", LAMBDA_PLATFORM,
            "--implementation", LAMBDA_IMPLEMENTATION,
            "--python-version", LAMBDA_PYTHON_VERSION,
            "--only-binary", ":all:",
            "--upgrade",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[bundle-lambda] WARNING: Platform-targeted install failed:\n{result.stderr[:400]}")
        return False
    return True


def install_host_platform(requirements_file: str, output_dir: str) -> None:
    """
    Standard pip install on the host platform.
    On Linux this is correct; on Windows this installs Windows binaries (may fail on Lambda).
    Used as fallback when manylinux wheels are not available on PyPI.
    """
    _run(
        [
            sys.executable, "-m", "pip", "install",
            "-r", requirements_file,
            "-t", output_dir,
            "--upgrade",
            "--quiet",
        ],
        check=True,
    )


def copy_python_sources(source_dir: str, output_dir: str) -> None:
    """Copy all .py files from source_dir into output_dir."""
    copied = []
    for filename in os.listdir(source_dir):
        if filename.endswith(".py"):
            src = os.path.join(source_dir, filename)
            dst = os.path.join(output_dir, filename)
            shutil.copy2(src, dst)
            copied.append(filename)
    print(f"[bundle-lambda] Copied {len(copied)} source file(s): {', '.join(copied)}")


def bundle(requirements_file: str, output_dir: str, source_dir: str) -> None:
    host_os = platform.system()
    print(f"[bundle-lambda] Host OS  : {host_os} ({platform.machine()})")
    print(f"[bundle-lambda] Target   : Lambda Python 3.12 ({LAMBDA_PLATFORM})")
    print(f"[bundle-lambda] Reqs     : {requirements_file}")
    print(f"[bundle-lambda] Source   : {source_dir}")
    print(f"[bundle-lambda] Output   : {output_dir}")

    os.makedirs(output_dir, exist_ok=True)

    if host_os == "Windows":
        print("[bundle-lambda] Windows detected → using --platform manylinux2014_x86_64")
        ok = install_linux_platform(requirements_file, output_dir)
        if not ok:
            print(
                "[bundle-lambda] WARNING: manylinux install failed for one or more packages.\n"
                "[bundle-lambda] Falling back to host-platform install.\n"
                "[bundle-lambda] Packages with native extensions may fail on Lambda!\n"
                "[bundle-lambda] Consider: (1) removing native deps, (2) using Docker bundling,\n"
                "[bundle-lambda]           or (3) ensuring all deps have manylinux PyPI wheels."
            )
            install_host_platform(requirements_file, output_dir)
    else:
        # Linux (CI/CD, native dev) or macOS — standard install
        # macOS + native deps: if you hit issues, set FORCE_LINUX_BUNDLE=1
        if os.environ.get("FORCE_LINUX_BUNDLE", "").lower() in ("1", "true", "yes"):
            print(f"[bundle-lambda] FORCE_LINUX_BUNDLE=1 → using --platform {LAMBDA_PLATFORM}")
            ok = install_linux_platform(requirements_file, output_dir)
            if not ok:
                install_host_platform(requirements_file, output_dir)
        else:
            print(f"[bundle-lambda] {host_os} detected → standard pip install")
            install_host_platform(requirements_file, output_dir)

    copy_python_sources(source_dir, output_dir)

    item_count = len(os.listdir(output_dir))
    print(f"[bundle-lambda] Done — {item_count} items in output dir")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python bundle-lambda.py <requirements.txt> <output_dir> <source_dir>")
        sys.exit(1)

    requirements_file = sys.argv[1]
    output_dir = sys.argv[2]
    source_dir = sys.argv[3]

    if not os.path.isfile(requirements_file):
        print(f"[bundle-lambda] ERROR: requirements file not found: {requirements_file}")
        sys.exit(1)
    if not os.path.isdir(source_dir):
        print(f"[bundle-lambda] ERROR: source dir not found: {source_dir}")
        sys.exit(1)

    bundle(requirements_file, output_dir, source_dir)
