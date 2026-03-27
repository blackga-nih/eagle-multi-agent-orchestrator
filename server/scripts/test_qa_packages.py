#!/usr/bin/env python3
"""
QA Package API Test Suite — runs against the deployed QA backend ALB.

Tests:
  1. Health check
  2. List packages
  3. Get package details
  4. Get package checklist
  5. List package documents
  6. Download package ZIP export
  7. Validate ZIP contents

Usage (from devbox inside VPC):
    python test_qa_packages.py
    python test_qa_packages.py --base-url http://custom-alb-url
    python test_qa_packages.py --tenant-id my-tenant --user-id my-user
"""
import argparse
import io
import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone

from typing import Optional, Tuple

import requests

# ── Defaults ──────────────────────────────────────────────────────────
QA_BACKEND_URL = os.getenv(
    "QA_BACKEND_URL",
    "http://internal-EagleC-Backe-tcOA80aBV9Xr-408603151.us-east-1.elb.amazonaws.com",
)
DEFAULT_TENANT = os.getenv("EAGLE_TENANT_ID", "nci")
DEFAULT_USER = os.getenv("EAGLE_USER_ID", "qa-tester")

# ── Result tracking ──────────────────────────────────────────────────
results = []  # type: list


def record(name: str, passed: bool, detail: str = "", duration_ms: int = 0):
    status = "PASS" if passed else "FAIL"
    icon = "✓" if passed else "✗"
    results.append({"name": name, "passed": passed, "detail": detail, "duration_ms": duration_ms})
    print(f"  {icon} {status}  {name} ({duration_ms}ms) {detail}")


def timed_request(method, url, **kwargs):
    # type: (str, str, ...) -> Tuple[Optional[requests.Response], int]
    """Make a request and return (response, elapsed_ms)."""
    t0 = time.monotonic()
    try:
        resp = requests.request(method, url, timeout=30, **kwargs)
        elapsed = int((time.monotonic() - t0) * 1000)
        return resp, elapsed
    except Exception as e:
        import traceback
        elapsed = int((time.monotonic() - t0) * 1000)
        print(f"    ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None, elapsed


def run_tests(base_url: str, tenant_id: str, user_id: str):
    headers = {
        "X-Tenant-Id": tenant_id,
        "X-User-Id": user_id,
    }

    print(f"\n{'='*70}")
    print(f"  EAGLE QA Package Test Suite")
    print(f"  Target:  {base_url}")
    print(f"  Tenant:  {tenant_id}")
    print(f"  User:    {user_id}")
    print(f"  Time:    {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*70}\n")

    # ── Test 1: Health check ──────────────────────────────────────────
    print("[1/7] Health Check")
    resp, ms = timed_request("GET", f"{base_url}/api/health")
    if resp is not None:
        record("health_check", resp.status_code == 200,
               f"status={resp.status_code}", ms)
        if resp.status_code == 200:
            try:
                health = resp.json()
                print(f"    Health response: {json.dumps(health, indent=2)[:500]}")
            except Exception:
                print(f"    Body: {resp.text[:300]}")
    else:
        record("health_check", False, "Connection failed", ms)
        print("\n  ✗ Cannot reach QA backend — aborting remaining tests.")
        return

    # ── Test 2: List packages ─────────────────────────────────────────
    print("\n[2/7] List Packages")
    resp, ms = timed_request("GET", f"{base_url}/api/packages", headers=headers)
    packages = []
    if resp is not None:
        ok = resp.status_code == 200
        try:
            packages = resp.json() if ok else []
        except Exception:
            packages = []
        record("list_packages", ok,
               f"status={resp.status_code}, count={len(packages)}", ms)
        if ok and packages:
            print(f"    Found {len(packages)} package(s)")
            for i, pkg in enumerate(packages[:5]):
                print(f"      [{i}] {pkg.get('package_id', '?')} — "
                      f"{pkg.get('title', 'untitled')[:50]} "
                      f"(status={pkg.get('status', '?')})")
        elif ok:
            print("    No packages found — some tests will be skipped.")
    else:
        record("list_packages", False, "Connection failed", ms)

    if not packages:
        print("\n  ⚠ No packages available — creating a test package for ZIP export testing.")

        # Create a test package
        print("\n[2b] Creating Test Package")
        create_body = {
            "title": "QA Test Package - ZIP Export Validation",
            "requirement_type": "services",
            "estimated_value": "150000",
            "notes": "Auto-created by QA test suite for ZIP export validation",
        }
        resp, ms = timed_request("POST", f"{base_url}/api/packages", headers=headers,
                                 json=create_body)
        if resp and resp.status_code == 200:
            new_pkg = resp.json()
            target_id = new_pkg.get("package_id", "")
            record("create_test_package", True,
                   f"package_id={target_id}", ms)
            print(f"    Created package: {target_id}")

            # Add test documents
            test_docs = [
                {
                    "doc_type": "sow",
                    "title": "Statement of Work",
                    "content": "# Statement of Work\n\n## 1. Purpose\nThis SOW defines the requirements for cloud hosting services.\n\n## 2. Scope\nThe contractor shall provide managed cloud infrastructure.\n\n## 3. Period of Performance\n12 months from date of award.\n\n## 4. Requirements\n- FedRAMP High authorized\n- 99.99% uptime SLA\n- 24/7 support\n",
                    "file_type": "md",
                    "change_source": "qa_test",
                },
                {
                    "doc_type": "igce",
                    "title": "Independent Government Cost Estimate",
                    "content": "# IGCE\n\n## Cost Breakdown\n| Item | Qty | Unit Cost | Total |\n|------|-----|-----------|-------|\n| Cloud Hosting (monthly) | 12 | $10,000 | $120,000 |\n| Support | 12 | $2,500 | $30,000 |\n| **Total** | | | **$150,000** |\n",
                    "file_type": "md",
                    "change_source": "qa_test",
                },
                {
                    "doc_type": "acquisition_plan",
                    "title": "Acquisition Plan",
                    "content": "# Acquisition Plan\n\n## 1. Background\nNCI requires FedRAMP-authorized cloud hosting services.\n\n## 2. Market Research\nThree vendors evaluated: AWS GovCloud, Azure Gov, Google Cloud.\n\n## 3. Acquisition Strategy\nFull and open competition, FAR Part 12 commercial items.\n\n## 4. Milestones\n- RFI: 30 days\n- RFP: 45 days\n- Evaluation: 30 days\n- Award: 15 days\n",
                    "file_type": "md",
                    "change_source": "qa_test",
                },
            ]

            for doc in test_docs:
                resp_doc, ms_doc = timed_request(
                    "POST",
                    f"{base_url}/api/packages/{target_id}/documents",
                    headers=headers,
                    json=doc,
                )
                if resp_doc and resp_doc.status_code == 200:
                    print(f"    + Added {doc['doc_type']}: {doc['title']}")
                else:
                    status = resp_doc.status_code if resp_doc else "N/A"
                    body = resp_doc.text[:200] if resp_doc else "Connection failed"
                    print(f"    ! Failed to add {doc['doc_type']}: HTTP {status} — {body}")

            packages = [new_pkg]
        else:
            status = resp.status_code if resp else "N/A"
            body = resp.text[:200] if resp else "Connection failed"
            record("create_test_package", False,
                   f"status={status}, body={body}", ms)
            print(f"    Failed to create test package: HTTP {status}")
            _print_summary()
            return

    # Pick the best package for testing (prefer one with documents)
    target_pkg = packages[0]
    target_id = target_pkg.get("package_id", "")
    print(f"\n    Target package: {target_id} — {target_pkg.get('title', '')[:60]}")

    # ── Test 3: Get package details ───────────────────────────────────
    print(f"\n[3/7] Get Package Details ({target_id})")
    resp, ms = timed_request("GET", f"{base_url}/api/packages/{target_id}", headers=headers)
    if resp is not None:
        ok = resp.status_code == 200
        record("get_package", ok, f"status={resp.status_code}", ms)
        if ok:
            detail = resp.json()
            print(f"    Title: {detail.get('title', '?')}")
            print(f"    Status: {detail.get('status', '?')}")
            print(f"    Pathway: {detail.get('acquisition_pathway', '?')}")
            print(f"    Value: {detail.get('estimated_value', '?')}")
    else:
        record("get_package", False, "Connection failed", ms)

    # ── Test 4: Package checklist ─────────────────────────────────────
    print(f"\n[4/7] Package Checklist ({target_id})")
    resp, ms = timed_request("GET", f"{base_url}/api/packages/{target_id}/checklist", headers=headers)
    if resp is not None:
        ok = resp.status_code == 200
        record("package_checklist", ok, f"status={resp.status_code}", ms)
        if ok:
            checklist = resp.json()
            print(f"    Checklist: {json.dumps(checklist, indent=2)[:500]}")
    else:
        record("package_checklist", False, "Connection failed", ms)

    # ── Test 5: List documents ────────────────────────────────────────
    print(f"\n[5/7] List Package Documents ({target_id})")
    resp, ms = timed_request("GET", f"{base_url}/api/packages/{target_id}/documents", headers=headers)
    docs = []
    if resp is not None:
        ok = resp.status_code == 200
        try:
            docs = resp.json() if ok else []
        except Exception:
            docs = []
        record("list_documents", ok,
               f"status={resp.status_code}, count={len(docs)}", ms)
        if ok and docs:
            for d in docs[:10]:
                print(f"      - {d.get('doc_type', '?')}: {d.get('title', '?')[:40]} "
                      f"(v{d.get('version', '?')}, {d.get('status', '?')})")
    else:
        record("list_documents", False, "Connection failed", ms)

    # ── Test 6: ZIP export ────────────────────────────────────────────
    print(f"\n[6/7] Export Package ZIP ({target_id})")
    resp, ms = timed_request("GET", f"{base_url}/api/packages/{target_id}/export/zip", headers=headers)
    zip_ok = False
    if resp is not None:
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "")
            cd = resp.headers.get("content-disposition", "")
            size = len(resp.content)
            zip_ok = "application/zip" in ct and size > 0
            record("export_zip", zip_ok,
                   f"status=200, size={size}B, content-type={ct}", ms)
            print(f"    Content-Disposition: {cd}")
            print(f"    Size: {size:,} bytes")
        elif resp.status_code == 404 and not docs:
            record("export_zip", True,
                   f"status=404 (expected — no documents with content)", ms)
            print("    Got 404 as expected — package has no documents with content.")
        else:
            record("export_zip", False,
                   f"status={resp.status_code}, body={resp.text[:200]}", ms)
    else:
        record("export_zip", False, "Connection failed", ms)

    # ── Test 7: Validate ZIP contents ─────────────────────────────────
    print(f"\n[7/7] Validate ZIP Contents")
    if zip_ok and resp:
        try:
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            names = zf.namelist()
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            record("validate_zip", len(names) > 0,
                   f"files={len(names)}, uncompressed={total_uncompressed:,}B", ms)
            print(f"    ZIP contains {len(names)} file(s):")
            for name in names:
                info = zf.getinfo(name)
                print(f"      - {name} ({info.file_size:,} bytes)")

            # Spot-check: try reading first file
            if names:
                first = names[0]
                data = zf.read(first)
                preview = data[:200].decode("utf-8", errors="replace")
                print(f"\n    Preview of {first}:")
                print(f"    {preview[:150]}...")
        except zipfile.BadZipFile as e:
            record("validate_zip", False, f"Invalid ZIP: {e}", 0)
        except Exception as e:
            record("validate_zip", False, f"Error: {e}", 0)
    elif not docs:
        record("validate_zip", True, "Skipped — no documents to export", 0)
    else:
        record("validate_zip", False, "No ZIP data to validate", 0)

    # ── Bonus: Test all packages for ZIP export ───────────────────────
    if len(packages) > 1:
        print(f"\n[Bonus] Scan all {len(packages)} packages for ZIP export")
        for pkg in packages:
            pid = pkg.get("package_id", "")
            title = pkg.get("title", "untitled")[:40]
            resp, ms = timed_request("GET", f"{base_url}/api/packages/{pid}/export/zip", headers=headers)
            if resp is not None:
                if resp.status_code == 200:
                    size = len(resp.content)
                    try:
                        zf = zipfile.ZipFile(io.BytesIO(resp.content))
                        n_files = len(zf.namelist())
                        print(f"    ✓ {pid} ({title}) — {size:,}B ZIP, {n_files} files")
                    except zipfile.BadZipFile:
                        print(f"    ✗ {pid} ({title}) — {size:,}B but INVALID ZIP")
                elif resp.status_code == 404:
                    print(f"    - {pid} ({title}) — 404 (no docs)")
                else:
                    print(f"    ✗ {pid} ({title}) — HTTP {resp.status_code}")
            else:
                print(f"    ✗ {pid} ({title}) — connection failed")

    _print_summary()


def _print_summary():
    print(f"\n{'='*70}")
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = len(results)
    total_ms = sum(r["duration_ms"] for r in results)
    print(f"  Results: {passed}/{total} passed, {failed} failed ({total_ms}ms total)")
    print(f"{'='*70}\n")

    if failed:
        print("  Failed tests:")
        for r in results:
            if not r["passed"]:
                print(f"    ✗ {r['name']}: {r['detail']}")
        print()

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EAGLE QA Package API Test Suite")
    parser.add_argument("--base-url", default=QA_BACKEND_URL, help="QA backend ALB URL")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT, help="Tenant ID")
    parser.add_argument("--user-id", default=DEFAULT_USER, help="User ID")
    args = parser.parse_args()

    run_tests(args.base_url, args.tenant_id, args.user_id)
