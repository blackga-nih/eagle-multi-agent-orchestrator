"""EAGLE Eval AWS Publisher — S3 archival + CloudWatch custom metrics.

Standalone module. Lazy-loads boto3 clients. All operations non-fatal
(try/except wrappers). Uses EVAL_S3_BUCKET env var
(default: eagle-eval-artifacts).

Public API:
    publish_eval_metrics(results, run_timestamp, total_cost_usd)
    archive_results_to_s3(local_path, run_timestamp)
    archive_videos_to_s3(video_base_dir, run_timestamp)
"""

import os
from typing import Optional

# ---------------------------------------------------------------------------
# Lazy boto3 clients
# ---------------------------------------------------------------------------
_cw_client = None
_s3_client = None

_BUCKET = os.environ.get("EVAL_S3_BUCKET", "eagle-eval-artifacts")
_NAMESPACE = "EAGLE/Eval"
_REGION = os.environ.get("AWS_REGION", "us-east-1")

# All 28 test names (must stay in sync with test_eagle_sdk_eval.py)
_TEST_NAMES = {
    1: "1_session_creation",
    2: "2_session_resume",
    3: "3_trace_observation",
    4: "4_subagent_orchestration",
    5: "5_cost_tracking",
    6: "6_tier_gated_tools",
    7: "7_skill_loading",
    8: "8_subagent_tool_tracking",
    9: "9_oa_intake_workflow",
    10: "10_legal_counsel_skill",
    11: "11_market_intelligence_skill",
    12: "12_tech_review_skill",
    13: "13_public_interest_skill",
    14: "14_document_generator_skill",
    15: "15_supervisor_multi_skill_chain",
    16: "16_s3_document_ops",
    17: "17_dynamodb_intake_ops",
    18: "18_cloudwatch_logs_ops",
    19: "19_document_generation",
    20: "20_cloudwatch_e2e_verification",
    21: "21_uc02_micro_purchase",
    22: "22_uc03_option_exercise",
    23: "23_uc04_contract_modification",
    24: "24_uc05_co_package_review",
    25: "25_uc07_contract_closeout",
    26: "26_uc08_shutdown_notification",
    27: "27_uc09_score_consolidation",
    28: "28_sdk_skill_subagent_orchestration",
}


def _get_cw():
    global _cw_client
    if _cw_client is None:
        import boto3
        _cw_client = boto3.client("cloudwatch", region_name=_REGION)
    return _cw_client


def _get_s3():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client("s3", region_name=_REGION)
    return _s3_client


# ---------------------------------------------------------------------------
# publish_eval_metrics
# ---------------------------------------------------------------------------

def publish_eval_metrics(
    results: dict,
    run_timestamp: str,
    total_cost_usd: float = 0.0,
) -> bool:
    """Publish eval metrics to CloudWatch EAGLE/Eval namespace.

    Returns True on success, False on failure (non-fatal).
    """
    try:
        passed = sum(1 for v in results.values() if v is True)
        failed = sum(1 for v in results.values() if v is False)
        skipped = sum(1 for v in results.values() if v is None)
        total = passed + failed + skipped
        pass_rate = (passed / total * 100) if total > 0 else 0.0

        metric_data = [
            # Aggregate pass rate (no dimensions — for dashboard trending)
            {"MetricName": "PassRate", "Value": pass_rate, "Unit": "Percent"},
            # Per-run pass rate
            {
                "MetricName": "PassRate",
                "Value": pass_rate,
                "Unit": "Percent",
                "Dimensions": [{"Name": "RunId", "Value": run_timestamp}],
            },
            {"MetricName": "TestsPassed", "Value": float(passed), "Unit": "Count"},
            {"MetricName": "TestsFailed", "Value": float(failed), "Unit": "Count"},
            {"MetricName": "TestsSkipped", "Value": float(skipped), "Unit": "Count"},
        ]

        if total_cost_usd > 0:
            metric_data.append(
                {"MetricName": "TotalCost", "Value": total_cost_usd, "Unit": "None"}
            )

        # Per-test status (1.0 = pass, 0.0 = fail/skip)
        for test_id, test_name in _TEST_NAMES.items():
            result_val = results.get(test_id)
            metric_data.append({
                "MetricName": "TestStatus",
                "Value": 1.0 if result_val is True else 0.0,
                "Unit": "None",
                "Dimensions": [{"Name": "TestName", "Value": test_name}],
            })

        _get_cw().put_metric_data(Namespace=_NAMESPACE, MetricData=metric_data)
        count = len(metric_data)
        print(f"CloudWatch Metrics: published {count} metrics to {_NAMESPACE}")
        return True
    except Exception as exc:
        print(f"CloudWatch Metrics: publish failed (non-fatal): {exc}")
        return False


# ---------------------------------------------------------------------------
# archive_results_to_s3
# ---------------------------------------------------------------------------

def archive_results_to_s3(
    local_path: str,
    run_timestamp: str,
) -> Optional[str]:
    """Upload results JSON to S3. Returns S3 URI or None on failure."""
    try:
        s3_key = f"eval/results/run-{run_timestamp}.json"
        _get_s3().upload_file(local_path, _BUCKET, s3_key)
        uri = f"s3://{_BUCKET}/{s3_key}"
        print(f"S3 Archive: uploaded results to {uri}")
        return uri
    except Exception as exc:
        print(f"S3 Archive: upload failed (non-fatal): {exc}")
        return None


# ---------------------------------------------------------------------------
# archive_videos_to_s3
# ---------------------------------------------------------------------------

def archive_videos_to_s3(
    video_base_dir: str,
    run_timestamp: str,
) -> int:
    """Walk video_base_dir for .webm/.mp4 files and upload to S3.

    S3 key: eval/videos/<run-ts>/<test_dir>/<file>
    Returns upload count.
    """
    count = 0
    if not os.path.isdir(video_base_dir):
        return count
    try:
        s3 = _get_s3()
        for dirpath, _dirs, files in os.walk(video_base_dir):
            for fname in files:
                if not fname.endswith((".webm", ".mp4")):
                    continue
                local = os.path.join(dirpath, fname)
                rel = os.path.relpath(local, video_base_dir).replace("\\", "/")
                s3_key = f"eval/videos/{run_timestamp}/{rel}"
                try:
                    s3.upload_file(local, _BUCKET, s3_key)
                    count += 1
                except Exception as exc:
                    print(f"S3 Archive: video upload failed for {rel} (non-fatal): {exc}")
        if count:
            print(f"S3 Archive: uploaded {count} video(s) to s3://{_BUCKET}/eval/videos/{run_timestamp}/")
    except Exception as exc:
        print(f"S3 Archive: video walk failed (non-fatal): {exc}")
    return count
