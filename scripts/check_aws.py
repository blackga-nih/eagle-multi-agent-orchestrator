#!/usr/bin/env python
"""AWS connectivity and resource check for the EAGLE platform.

Verifies credentials, core resources (nci-documents, eagle table, ECS),
and EagleStorageStack resources (eagle-documents-dev, metadata table, Lambda).
"""

import sys
import boto3

REGION = "us-east-1"
results = []


def check(name, fn):
    try:
        detail = fn()
        results.append((name, "OK", detail or ""))
    except Exception as e:
        results.append((name, "FAIL", str(e)[:80]))


s3 = boto3.client("s3", region_name=REGION)
ddb = boto3.client("dynamodb", region_name=REGION)
ecs = boto3.client("ecs", region_name=REGION)
lmb = boto3.client("lambda", region_name=REGION)
sts = boto3.client("sts", region_name=REGION)

check("AWS Identity", lambda: f'Account {sts.get_caller_identity()["Account"]}')
check("S3 nci-documents", lambda: (s3.head_bucket(Bucket="nci-documents"), "Accessible")[1])
check("S3 eagle-documents-dev", lambda: (s3.head_bucket(Bucket="eagle-documents-dev"), "Accessible")[1])
check("DynamoDB eagle", lambda: ddb.describe_table(TableName="eagle")["Table"]["TableStatus"])
check("DynamoDB eagle-document-metadata-dev", lambda: ddb.describe_table(TableName="eagle-document-metadata-dev")["Table"]["TableStatus"])
check("Lambda eagle-metadata-extractor-dev", lambda: lmb.get_function(FunctionName="eagle-metadata-extractor-dev")["Configuration"]["State"])

svc_resp = None
try:
    svc_resp = ecs.describe_services(
        cluster="eagle-dev",
        services=["eagle-backend-dev", "eagle-frontend-dev"],
    )
    for svc in svc_resp["services"]:
        results.append((
            f'ECS {svc["serviceName"]}',
            "OK",
            f'{svc["runningCount"]}/{svc["desiredCount"]} running',
        ))
except Exception as e:
    results.append(("ECS eagle-dev", "FAIL", str(e)[:80]))

print("=== EAGLE AWS Check ===")
print(f"{'Resource':<45s} {'Status':<6s} {'Detail'}")
print("-" * 80)
for name, status, detail in results:
    indicator = "✓" if status == "OK" else "✗"
    print(f"  {indicator} {name:<43s} {status:<6s} {detail}")

ok_count = sum(1 for _, s, _ in results if s == "OK")
fail_count = len(results) - ok_count
print()
print(f"Summary: {ok_count}/{len(results)} OK", end="")
if fail_count:
    print(f"  — {fail_count} FAIL(s). Run 'just cdk-deploy' if StorageStack resources are missing.")
    sys.exit(1)
else:
    print("  — All checks passed.")
